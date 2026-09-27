"""Router de modelos por etapa e por erro (backend-22, pedido do dono 2026-09-27 12:39 BRT).

Dados: desafio_itau/politica/cotas-gemini-v1.json (limites do painel AI Studio, IDs confirmados na API, sonda com o
corpo real). Nada de ordem em `if`: a ordem por etapa, a escolha por status e os resfriamentos vêm do ficheiro.

- `escolher(etapa, excluir, status)`: primeiro modelo da ordem da etapa que não está em resfriamento nem no teto de RPM
  do painel (contado neste processo, janela de 60 s, com `rpm_margem`); depois de timeout (504) escolhe o mais rápido
  (`latencia_ref_ms`). None = nenhum disponível.
- `falhou(modelo, status, cota, retry_s)`: resfriamento — 429 de cota diária 900 s; 429 por minuto/sem tipo usa o
  `retryDelay` do Google quando vem; 504, 503/5xx e 404 têm o seu tempo; 400 não resfria (erro do nosso pedido).
Quem decide SE há nova chamada continua a ser erros_api-v1.json (no máximo uma, nunca o mesmo pedido ao mesmo modelo);
o router só decide QUAL modelo. Pular um modelo em resfriamento não é chamada.
"""
import json
import threading
import time
from collections import deque
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ARQUIVO = Path(__file__).resolve().parents[2] / 'desafio_itau' / 'politica' / 'cotas-gemini-v1.json'
ETAPAS = ('input_guard', 'output_guard', 'generate')


class _E(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class Painel(_E):
    rpm: int = Field(ge=0)
    rpm_uso: int = Field(ge=0)
    tpm: int = Field(ge=0)
    tpm_uso: int = Field(ge=0)
    rpd: int = Field(ge=0)
    rpd_uso: int = Field(ge=0)


class Sonda(_E):
    http: int
    latencia_ms: int
    nota: str


class Modelo(_E):
    rotulo: str
    painel: Painel
    sonda: Sonda
    latencia_ref_ms: int | None
    apto: bool


class Resfriamento(_E):
    cota_dia: int = Field(ge=0)
    cota_minuto_padrao: int = Field(ge=0)
    timeout: int = Field(ge=0)
    indisponivel: int = Field(ge=0)
    nao_encontrado: int = Field(ge=0)


class Router(_E):
    nota: str
    etapas: dict[Literal['input_guard', 'output_guard', 'generate'], list[str]]
    escolha_por_status: dict[str, Literal['ordem', 'mais_rapido']]
    resfriamento_s: Resfriamento
    rpm_margem: int = Field(ge=0)


class Cotas(_E):
    schema_version: Literal['1.0']
    id: str
    versao: str
    natureza: Literal['dados_operacionais']
    selo: dict[str, str]
    modelos: dict[str, Modelo]
    sem_cota_no_painel: list[str]
    router: Router


@lru_cache(maxsize=1)
def carregar():
    return validar(json.loads(ARQUIVO.read_text(encoding='utf-8')))


def validar(bruto):
    """Schema estrito + toda etapa com ordem e só modelos `apto` (sondados com o corpo real)."""
    dados = Cotas.model_validate(bruto)
    for etapa in ETAPAS:
        ordem = dados.router.etapas.get(etapa) or []
        if not ordem:
            raise ValueError(f'Router sem ordem para {etapa}')
        for m in ordem:
            if m not in dados.modelos or not dados.modelos[m].apto:
                raise ValueError(f'Modelo fora da lista apta: {m}')
    return dados


class Roteador:
    def __init__(self, dados=None, relogio=time.monotonic):
        self.dados = dados or carregar()
        self.relogio = relogio
        self.resfriado = {}  # modelo -> (até, motivo, status)
        self.usos = {}       # modelo -> deque de instantes das chamadas reais (janela 60 s)
        self.ultimo = {}     # etapa -> modelo que respondeu por último
        self.tentativa = {}  # etapa -> {modelo, resultado} da última tentativa (sucesso ou falha)
        self._lock = threading.Lock()

    def modelos(self):
        return sorted({m for ordem in self.dados.router.etapas.values() for m in ordem})

    def _rpm(self, modelo, agora):
        fila = self.usos.setdefault(modelo, deque())
        while fila and agora - fila[0] >= 60:
            fila.popleft()
        return len(fila)

    def bloqueio(self, modelo):
        """None se disponível; senão o status que explica o bloqueio (429 cota/RPM, 504 timeout, 503/404)."""
        agora = self.relogio()
        with self._lock:
            r = self.resfriado.get(modelo)
            if r and r[0] > agora:
                return r[2]
            rpm = self.dados.modelos[modelo].painel.rpm
            if rpm and self._rpm(modelo, agora) >= max(1, rpm - self.dados.router.rpm_margem):
                return 429
        return None

    def escolher(self, etapa, excluir=(), status=None):
        ordem = self.dados.router.etapas[etapa]
        livres = [m for m in ordem if m not in excluir and self.bloqueio(m) is None]
        if not livres:
            return None
        if self.dados.router.escolha_por_status.get(str(status)) == 'mais_rapido':
            ref = lambda m: self.dados.modelos[m].latencia_ref_ms or 10 ** 9
            return min(livres, key=lambda m: (ref(m), ordem.index(m)))
        return livres[0]

    def motivo_sem_modelo(self, etapa):
        """Todos bloqueados: 429 se algum está sem cota (o front espera e tenta), senão o primeiro motivo."""
        motivos = [self.bloqueio(m) for m in self.dados.router.etapas[etapa]]
        motivos = [s for s in motivos if s]
        return 429 if 429 in motivos else (motivos[0] if motivos else 503)

    def chamou(self, modelo):
        with self._lock:
            self.usos.setdefault(modelo, deque()).append(self.relogio())

    def respondeu(self, etapa, modelo):
        self.ultimo[etapa] = modelo

    def tentou(self, etapa, modelo, resultado):
        self.tentativa[etapa] = {'modelo': modelo, 'resultado': resultado}

    def falhou(self, modelo, status, cota=None, retry_s=None):
        cfg = self.dados.router.resfriamento_s
        if status == 429:
            motivo, segundos = ('cota_dia', cfg.cota_dia) if cota == 'dia' else \
                ('cota_minuto', retry_s or cfg.cota_minuto_padrao)
        elif status == 504:
            motivo, segundos = 'timeout', cfg.timeout
        elif status == 404:
            motivo, segundos = 'nao_encontrado', cfg.nao_encontrado
        elif isinstance(status, int) and status >= 500:
            motivo, segundos = 'indisponivel', cfg.indisponivel
        else:
            return  # 400 e falhas sem status: erro do pedido/saída, não do modelo
        with self._lock:
            self.resfriado[modelo] = (self.relogio() + segundos, motivo, status)

    def estado(self):
        """Para GET conversas/status/: só modelos, números e motivos."""
        agora = self.relogio()
        with self._lock:
            resfr = {m: {'restam_s': round(ate - agora), 'motivo': motivo}
                     for m, (ate, motivo, _s) in self.resfriado.items() if ate > agora}
            rpm = {m: self._rpm(m, agora) for m in list(self.usos)}
        # Toda etapa aparece (null = nenhuma resposta válida desde o arranque). `proximo_por_etapa`: quem seria
        # chamado agora (sem chamar). `ultima_tentativa_por_etapa`: modelo e resultado da última tentativa, inclusive
        # falha — antes, etapa que só falhou não aparecia (visto na :8000 às 13:09).
        return {'dados': f'{self.dados.id}@{self.dados.versao}',
                'ordem_por_etapa': {e: list(o) for e, o in self.dados.router.etapas.items()},
                'ultimo_modelo_por_etapa': {e: self.ultimo.get(e) for e in ETAPAS},
                'ultima_tentativa_por_etapa': {e: self.tentativa.get(e) for e in ETAPAS},
                'proximo_por_etapa': {e: self.escolher(e) for e in ETAPAS},
                'resfriamentos': resfr,
                'rpm_no_processo': {m: n for m, n in rpm.items() if n}}
