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


ACOES_CLIENTE = Literal['reformular', 'reiniciar_sessao', 'aguardar_e_tentar_novamente', 'aguardar_ou_encaminhar',
                        'nao_repetir', 'enviar_como_nova']


class TipoErro(_Estrito):
    """Código de máquina estável para o front (1.2.0). `linha` aponta a linha de `erros` (ou 'nao_classificado') que dá
    nome, espera e encaminhamento; `acao_cliente`/`mensagem_cliente` só quando o tipo precisa de outro texto."""
    codigo: int = Field(ge=400, le=599)
    http: int = Field(ge=400, le=599)
    linha: Literal['400', '401', '403', '404', '405', '409', '429', '503', '504', 'nao_classificado']
    origem: Literal['api', 'provedor']
    descricao: str
    acao_cliente: ACOES_CLIENTE | None = None
    mensagem_cliente: str | None = Field(default=None, min_length=1, max_length=300)


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
    tipos: dict[str, TipoErro]


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


TIPO_API_POR_STATUS = {400: 'schema', 401: 'sessao_ausente', 403: 'acao_indisponivel', 404: 'nao_encontrado',
                       405: 'metodo_nao_permitido', 409: 'conflito_idempotencia', 429: 'rate_limit_usuario',
                       504: 'timeout_provedor'}


def tipo_de(status, origem='api'):
    """Status + origem -> tipo estável (1.2.0). Provedor: 429 cota, 504 timeout, o resto indisponível."""
    if origem == 'provedor':
        return {429: 'cota_provedor', 504: 'timeout_provedor'}.get(status, 'provedor_indisponivel')
    return TIPO_API_POR_STATUS.get(status, 'interno')


def http_de(tipo):
    """HTTP da resposta ao front para o tipo (tabela `tipos`)."""
    return carregar().tipos[tipo].http


def erro_api(status, origem='api', tipo=None):
    """Bloco aditivo do envelope. `origem`: 'provedor' (falha do Gemini) ou 'api' (validação da nossa rota).

    None só para sucesso da nossa API (status None ou < 400, sem `tipo`). Qualquer falha tem bloco com `tipo` e
    `codigo` numérico NUNCA null (1.2.0): falha do provedor sem status sai com 503. Nome, espera e encaminhamento vêm
    da linha do status real (fora da tabela ou das `origens` -> NAO_CLASSIFICADO, como na 1.1.0); o tipo só troca a
    ação/mensagem quando a tabela `tipos` diz."""
    if tipo is None and origem == 'api' and (status is None or int(status) < 400):
        return None
    pol = carregar()
    tipo = tipo or tipo_de(status, origem)
    tt = pol.tipos[tipo]
    linha = status
    if status is None and tipo != tipo_de(None, origem) and tt.linha.isdigit():
        # 1.3.0: sem status HTTP, um tipo ESPECÍFICO (ex.: resposta_modelo_invalida) usa a linha dele; só o tipo
        # genérico da origem (provedor_indisponivel / interno) continua NAO_CLASSIFICADO (D7).
        linha = int(tt.linha)
    t = tratamento(linha) if linha is not None else None
    if not t or origem not in t.origens:
        t = pol.nao_classificado
    acao = tt.acao_cliente or t.acao_cliente
    mensagem = tt.mensagem_cliente or t.mensagem_cliente
    codigo = int(status) if isinstance(status, int) and not isinstance(status, bool) and status >= 400 else tt.codigo
    return {'codigo': codigo, 'tipo': tipo, 'nome': t.nome, 'origem': origem,
            'acao_cliente': acao,
            'tentar_novamente_em_s': t.espera_s if acao.startswith('aguardar') else None,
            'encaminhar_humano': t.encaminhar_humano,
            'mensagem': mensagem.format(espera_s=t.espera_s),
            'politica': f'{pol.id}@{pol.versao}'}
