"""Router de modelos por etapa e por erro (backend-22, pedido do dono 2026-09-27 12:39 BRT).

Dados: desafio_itau/politica/cotas-gemini-v1.json (limites do painel AI Studio, IDs confirmados na API, sonda com o
corpo real). Nada de ordem em `if`: a ordem por etapa, a escolha por status e os resfriamentos vêm do ficheiro.

- `escolher(etapa, excluir, status)`: primeiro modelo da ordem da etapa que não está em resfriamento nem no teto de RPM
  do painel (contado neste processo, janela de 60 s, com `rpm_margem`); depois de timeout (504) escolhe o mais rápido
  (`latencia_ref_ms`). None = nenhum disponível.
- `falhou(modelo, status, cota, retry_s)`: resfriamento — 429 de cota diária 900 s; 429 por minuto/sem tipo usa o
  `retryDelay` do Google quando vem; 504, 503/5xx e 404 têm o seu tempo; 400 não resfria (erro do nosso pedido).
Quem decide SE há nova chamada continua a ser erros_api-v1.json (1.4.0: pela ordem, dentro do prazo do turno, nunca o
mesmo modelo duas vezes na etapa); o router só decide QUAL modelo. Pular um modelo em resfriamento não é chamada.
- 1.1.0 dos dados (dono 14:09/14:11): `capacidades` por modelo (RPM, etapas, timeout, tokens, latência mediana, falhas)
  lidas aqui; resfriamento transitório (timeout, 5xx, 429 por minuto) só despromove — `ultimo_recurso` tenta o de menor
  espera quando todos estão bloqueados; `espera_restante`/`motivo_bloqueio` vão para o Retry-After do front.
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


STATUS_DO_MOTIVO = {'cota_dia': 429, 'cota_minuto': 429, 'rpm_processo': 429, 'timeout': 504, 'indisponivel': 503,
                    'nao_encontrado': 404}
MOTIVOS = Literal['cota_dia', 'cota_minuto', 'timeout', 'indisponivel', 'nao_encontrado']
ETAPA = Literal['input_guard', 'output_guard', 'generate']


class Router(_E):
    nota: str
    etapas: dict[ETAPA, list[str]]
    escolha_por_status: dict[str, Literal['ordem', 'mais_rapido']]
    resfriamento_s: Resfriamento
    rpm_margem: int = Field(ge=0)
    # 1.1.0 (dono 14:09): resfriamento transitório só despromove; com todos bloqueados, o de menor espera transitória
    # é tentado como último recurso. Fora desta lista (cota_dia, nao_encontrado) o modelo fica mesmo excluído.
    transitorios: list[MOTIVOS] = []
    # 1.2.0 (live 14:25): teto da tentativa = min(timeout_s, max(teto_piso_s, teto_fator_mediana × mediana medida)).
    teto_fator_mediana: float = Field(default=3.0, gt=0)
    teto_piso_s: float = Field(default=6.0, gt=0)
    # 1.2.0: etapas cuja ordem TEM de seguir a latência mediana medida (modelos NAO_MEDIDO não entram na conta).
    ordem_por_latencia: list[ETAPA] = []


class Limite(_E):
    valor: int | None = Field(default=None, ge=0)
    fonte: str
    estado: Literal['observado', 'NAO_MEDIDO']


class Latencia(_E):
    valor_ms: int | None = Field(ge=0)
    n: int = Field(ge=0)
    fonte: str
    estado: Literal['observado', 'NAO_MEDIDO']


class Pensamento(_E):
    emite: Literal['sim', 'nao', 'NAO_MEDIDO']
    fonte: str


class Capacidade(_E):
    """O que o modelo aguenta e como falhou (1.1.0, dono 14:11). Lido pelo router: `limites.rpm` (teto de RPM do
    processo), `etapas` (a ordem só pode ter quem serve a etapa), `timeout_s` (teto da tentativa),
    `max_output_tokens`, `latencia_mediana_ms` (o mais rápido depois de timeout)."""
    limites: dict[Literal['rpm', 'tpm', 'rpd'], Limite]
    etapas: dict[ETAPA, str]
    pensamento: Pensamento
    max_output_tokens: dict[Literal['guard', 'generate'], int]
    timeout_s: dict[ETAPA, int]
    latencia_mediana_ms: dict[ETAPA, Latencia]
    falhas_observadas: list[str]


class Cotas(_E):
    schema_version: Literal['1.0']
    id: str
    versao: str
    natureza: Literal['dados_operacionais']
    selo: dict[str, str]
    modelos: dict[str, Modelo]
    sem_cota_no_painel: list[str]
    router: Router
    capacidades: dict[str, Capacidade] = {}


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
            cap = dados.capacidades.get(m)
            if dados.capacidades and (cap is None or etapa not in cap.etapas or etapa not in cap.timeout_s):
                raise ValueError(f'Modelo {m} na ordem de {etapa} sem capacidade declarada para a etapa')
        if etapa in dados.router.ordem_por_latencia:
            medidas = [dados.capacidades[m].latencia_mediana_ms.get(etapa) for m in ordem]
            valores = [x.valor_ms for x in medidas if x is not None and x.valor_ms is not None]
            if valores != sorted(valores):
                raise ValueError(f'Ordem de {etapa} fora da latência mediana medida: {valores}')
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

    def rpm_teto(self, modelo):
        """RPM do painel: de `capacidades` (1.1.0) quando declarado, senão do bloco `painel`."""
        cap = self.dados.capacidades.get(modelo)
        valor = cap.limites['rpm'].valor if cap and 'rpm' in cap.limites else None
        return valor if valor is not None else self.dados.modelos[modelo].painel.rpm

    def _limite_rpm(self, modelo):
        rpm = self.rpm_teto(modelo)
        return max(1, rpm - self.dados.router.rpm_margem) if rpm else None

    def timeout_s(self, modelo, etapa):
        cap = self.dados.capacidades.get(modelo)
        return cap.timeout_s.get(etapa) if cap else None

    def teto_tentativa(self, modelo, etapa):
        """Teto de UMA tentativa (live 14:25: 3.1-flash-lite gastou 15,8 e 20,1 s no generate, mediana 3,7 s):
        min(timeout_s da etapa, max(piso, fator × mediana medida)). Mediana NAO_MEDIDO -> timeout_s da etapa."""
        teto = self.timeout_s(modelo, etapa)
        cap = self.dados.capacidades.get(modelo)
        medida = cap.latencia_mediana_ms.get(etapa) if cap else None
        if teto is None or medida is None or medida.valor_ms is None:
            return teto
        r = self.dados.router
        return min(teto, max(r.teto_piso_s, r.teto_fator_mediana * medida.valor_ms / 1000))

    def max_output_tokens(self, modelo, papel):
        cap = self.dados.capacidades.get(modelo)
        return cap.max_output_tokens.get(papel) if cap else None

    def _latencia(self, modelo, etapa):
        cap = self.dados.capacidades.get(modelo)
        medida = cap.latencia_mediana_ms.get(etapa) if cap else None
        if medida is not None and medida.valor_ms is not None:
            return medida.valor_ms
        return self.dados.modelos[modelo].latencia_ref_ms or 10 ** 9

    def bloqueio(self, modelo):
        """None se disponível; senão o status que explica o bloqueio (429 cota/RPM, 504 timeout, 503/404)."""
        agora = self.relogio()
        with self._lock:
            r = self.resfriado.get(modelo)
            if r and r[0] > agora:
                return r[2]
            limite = self._limite_rpm(modelo)
            if limite and self._rpm(modelo, agora) >= limite:
                return 429
        return None

    def _espera(self, modelo, agora):
        """(segundos até ficar livre, motivo) — 0 se livre. Chamar com o lock."""
        espera, motivo = 0.0, None
        r = self.resfriado.get(modelo)
        if r and r[0] > agora:
            espera, motivo = r[0] - agora, r[1]
        limite = self._limite_rpm(modelo)
        fila = self.usos.get(modelo)
        if limite and fila is not None and self._rpm(modelo, agora) >= limite:
            livre_em = fila[len(fila) - limite] + 60 - agora
            if livre_em > espera:
                espera, motivo = livre_em, 'rpm_processo'
        return espera, motivo

    def escolher(self, etapa, excluir=(), status=None):
        """Primeiro livre da ordem (ou o mais rápido depois de timeout). Nenhum livre: ÚLTIMO RECURSO (1.1.0, dono
        14:09) — o de menor espera entre os resfriados por motivo transitório (`router.transitorios`: timeout,
        5xx, 429 por minuto), nunca cota_dia/404 nem o teto de RPM do processo, nunca um já tentado na etapa."""
        ordem = self.dados.router.etapas[etapa]
        livres = [m for m in ordem if m not in excluir and self.bloqueio(m) is None]
        if not livres:
            return self.ultimo_recurso(etapa, excluir)
        if self.dados.router.escolha_por_status.get(str(status)) == 'mais_rapido':
            return min(livres, key=lambda m: (self._latencia(m, etapa), ordem.index(m)))
        return livres[0]

    def ultimo_recurso(self, etapa, excluir=()):
        agora, transitorios = self.relogio(), set(self.dados.router.transitorios)
        candidatos = []
        with self._lock:
            for m in self.dados.router.etapas[etapa]:
                if m in excluir:
                    continue
                espera, motivo = self._espera(m, agora)
                if motivo in transitorios:
                    candidatos.append((espera, m))
        return min(candidatos)[1] if candidatos else None

    def espera_restante(self, etapa):
        """Menor espera real (s, inteiro >= 1) até algum modelo da etapa ficar livre; None se algum já está livre.
        Vai para o Retry-After / erro_api.tentar_novamente_em_s (1.1.0: antes era o fixo de 30 s da política)."""
        agora = self.relogio()
        with self._lock:
            esperas = [self._espera(m, agora)[0] for m in self.dados.router.etapas[etapa]]
        menor = min(esperas) if esperas else 0
        return max(1, int(menor + 0.999)) if menor > 0 else None

    def motivo_bloqueio(self, etapa, status=None):
        """'cota_dia' quando TODOS os modelos da etapa estão sem cota do dia; senão o motivo do de menor espera.
        Com `status`, só motivos que dão esse status (429 -> cota_*/rpm_processo; nunca 'timeout' num 429)."""
        agora = self.relogio()
        with self._lock:
            pares = [self._espera(m, agora) for m in self.dados.router.etapas[etapa]]
        motivos = [mo for _e, mo in pares]
        if motivos and all(mo == 'cota_dia' for mo in motivos):
            return 'cota_dia'
        ativos = [(e, mo) for e, mo in pares if mo and (status is None or STATUS_DO_MOTIVO.get(mo) == status)]
        return min(ativos)[1] if ativos else None

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
                'rpm_no_processo': {m: n for m, n in rpm.items() if n},
                'capacidades': self.capacidades_ao_vivo()}

    def capacidades_ao_vivo(self):
        """capacidades do ficheiro + estado vivo: livre | resfriando {motivo, restam_s} | rpm_usado (dono 14:11)."""
        agora, saida = self.relogio(), {}
        for m, cap in self.dados.capacidades.items():
            with self._lock:
                espera, motivo = self._espera(m, agora)
                usado = self._rpm(m, agora)
            vivo = {'estado': 'livre' if not motivo else 'resfriando', 'rpm_usado': usado,
                    'rpm_limite_processo': self._limite_rpm(m)}
            if motivo:
                vivo.update(motivo=motivo, restam_s=max(1, int(espera + 0.999)),
                            transitorio=motivo in self.dados.router.transitorios)
            saida[m] = {**cap.model_dump(), 'agora': vivo}
        return saida
