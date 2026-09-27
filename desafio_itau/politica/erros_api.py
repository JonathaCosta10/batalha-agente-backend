"""Tratamento conhecido de erros de API (erros_api-v1.json): 400, 404, 429, 503 e 504.

- `status_de(erro)`: exceção do transporte -> status HTTP (ErroProvedor.code; timeout -> 504; outro -> None).
- `tratamento(status)`: a linha da política, ou None para status sem tratamento conhecido.
- `pode_nova_chamada(status, ja_feitas)`: True só se a ação do servidor admite nova chamada e o limite
  (novas_chamadas_max = 1) não foi usado. A nova chamada NUNCA é o mesmo pedido ao mesmo modelo.
- `erro_api(status)`: bloco público do envelope — o que o cliente pode fazer, sem detalhe do provedor.
"""
import asyncio
import json
import socket
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ARQUIVO = Path(__file__).with_name('erros_api-v1.json')
COM_NOVA_CHAMADA = ('proximo_modelo', 'aguardar_e_proximo_modelo')


class _Estrito(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class Tratamento(_Estrito):
    nome: Literal['BadRequest', 'Unauthorized', 'Forbidden', 'NotFound', 'MethodNotAllowed', 'Conflict',
                  'TooManyRequests', 'ServiceUnavailable', 'GatewayTimeout', 'NAO_CLASSIFICADO']
    # De onde o status pode vir com ESTE significado; fora disso vira NAO_CLASSIFICADO (401 do provedor = chave).
    origens: list[Literal['api', 'provedor']] = ['api', 'provedor']
    causa_provavel: str
    repetir_mesmo_pedido: Literal[False]
    acao_servidor: Literal['proximo_modelo', 'aguardar_e_proximo_modelo', 'resposta_segura']
    solucao_possivel: str
    espera_s: int = Field(ge=0, le=600)
    acao_cliente: Literal['reformular', 'reiniciar_sessao', 'aguardar_e_tentar_novamente', 'aguardar_ou_encaminhar',
                          'nao_repetir', 'enviar_como_nova']
    encaminhar_humano: bool
    mensagem_cliente: str = Field(min_length=1, max_length=300)


class Limites(_Estrito):
    novas_chamadas_max: int = Field(ge=0, le=1)
    espera_max_no_servidor_s: int = Field(ge=0, le=5)
    status_de_timeout_local: Literal[504]


class Politica(_Estrito):
    schema_version: Literal['1.0']
    id: str
    versao: str = Field(pattern=r'^\d+\.\d+\.\d+$')
    natureza: Literal['politica_operacional']
    aviso: str
    historico: str
    limites: Limites
    erros: dict[Literal['400', '401', '403', '404', '405', '409', '429', '503', '504'], Tratamento]
    nao_classificado: Tratamento


@lru_cache(maxsize=1)
def carregar() -> Politica:
    return Politica.model_validate(json.loads(ARQUIVO.read_text(encoding='utf-8')))


def status_de(erro):
    codigo = getattr(erro, 'code', None)
    if isinstance(codigo, int) and not isinstance(codigo, bool):
        return codigo
    if isinstance(erro, (TimeoutError, socket.timeout, asyncio.TimeoutError)) or \
            isinstance(getattr(erro, 'reason', None), (TimeoutError, socket.timeout)):
        return carregar().limites.status_de_timeout_local
    return None


def tratamento(status):
    return carregar().erros.get(str(status)) if status is not None else None


def pode_nova_chamada(status, ja_feitas=0):
    t = tratamento(status)
    return bool(t) and t.acao_servidor in COM_NOVA_CHAMADA and ja_feitas < carregar().limites.novas_chamadas_max


def espera_no_servidor(status):
    """Segundos a esperar antes da nova chamada: só `aguardar_e_proximo_modelo`, limitado ao teto da política."""
    t = tratamento(status)
    if not t or t.acao_servidor != 'aguardar_e_proximo_modelo':
        return 0
    return min(t.espera_s, carregar().limites.espera_max_no_servidor_s)


def erro_api(status, origem='api'):
    """Bloco aditivo do envelope. `origem`: 'provedor' (falha do Gemini) ou 'api' (validação da nossa rota).

    None só para sucesso da nossa API (status None ou < 400). Qualquer falha tem bloco: status fora da tabela, ou
    fora das `origens` da linha, vira NAO_CLASSIFICADO com o código real (null se a exceção não tinha status)."""
    if origem == 'api' and (status is None or int(status) < 400):
        return None
    t = tratamento(status)
    if not t or origem not in t.origens:
        t = carregar().nao_classificado
    return {'codigo': int(status) if status is not None else None, 'nome': t.nome, 'origem': origem,
            'acao_cliente': t.acao_cliente,
            'tentar_novamente_em_s': t.espera_s if t.acao_cliente.startswith('aguardar') else None,
            'encaminhar_humano': t.encaminhar_humano,
            'mensagem': t.mensagem_cliente.format(espera_s=t.espera_s),
            'politica': f'{carregar().id}@{carregar().versao}'}
