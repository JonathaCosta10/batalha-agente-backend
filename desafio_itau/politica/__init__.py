"""Política operacional versionada: limiares, referências, hipóteses e tabela de estados — fonte única.

Os valores ficam em `operacional-v1.json` (configuração de política, não fato externo). Este módulo:
- valida o JSON com schemas estritos (tipo errado, campo desconhecido ou operador fora da lista: ValueError);
- devolve parâmetros como Decimal (texto no JSON, nunca float lido do arquivo);
- avalia condições tipadas por uma tabela fixa de operadores — nunca `eval` de expressão vinda de documento;
- trata indicador ausente/None como NAO_MEDIDO (resultado None), nunca como zero.

Consumidores que antes tinham a constante no próprio arquivo (t3.LIMIAR_SURPLUS, interacao_dados.LIMIAR_*,
projection) leem daqui; tests/test_politica_operacional.py::Equivalencia prova que os valores não mudaram.
"""
import hashlib
import json
import operator
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

PASTA = Path(__file__).parent
ARQUIVO = PASTA / 'operacional-v1.json'
OPERADORES = {'<': operator.lt, '<=': operator.le, '>': operator.gt, '>=': operator.ge, '==': operator.eq,
              '!=': operator.ne}


class _Estrito(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class Parametro(_Estrito):
    valor: str = Field(pattern=r'^-?\d{1,12}(?:\.\d{1,6})?$')
    unidade: Literal['pct', 'fracao', 'reais', 'meses', 'contagem']

    @property
    def decimal(self) -> Decimal:
        return Decimal(self.valor)


class Comparacao(_Estrito):
    indicador: str = Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')
    operador: Literal['<', '<=', '>', '>=', '==', '!=']
    parametro: str = Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')


class Qualquer(_Estrito):
    qualquer: list['Condicao'] = Field(min_length=1, max_length=8)


class Todas(_Estrito):
    todas: list['Condicao'] = Field(min_length=1, max_length=8)


Condicao = Union[Comparacao, Qualquer, Todas]
Qualquer.model_rebuild()
Todas.model_rebuild()


class Origem(_Estrito):
    arquivo: str = Field(min_length=1, max_length=200)
    secao: str = Field(min_length=1, max_length=200)


class Regra(_Estrito):
    rule_id: str = Field(pattern=r'^[a-z0-9_]+(?:\.[a-z0-9_]+)+$')
    versao: str = Field(pattern=r'^\d+\.\d+\.\d+$')
    tipo: Literal['limiar', 'referencia', 'hipotese', 'tabela_decisao']
    descricao: str = Field(min_length=1, max_length=400)
    parametros: dict[str, Parametro] = Field(min_length=1)
    condicao: Condicao | None
    acao: str = Field(min_length=1, max_length=80)
    prioridade: int = Field(ge=0, le=1000)
    justificativa_publica: str = Field(min_length=1, max_length=240)
    origem: list[Origem] = Field(min_length=1)
    testes: list[str] = Field(min_length=1)

    @field_validator('condicao')
    @classmethod
    def _parametros_existem(cls, condicao, info):
        nomes = set((info.data.get('parametros') or {}))
        for comparacao in _folhas(condicao):
            if comparacao.parametro not in nomes:
                raise ValueError(f'condição cita parâmetro inexistente: {comparacao.parametro}')
        return condicao


class Estado(_Estrito):
    acoes_permitidas: list[str] = Field(max_length=8)
    descricao: str = Field(min_length=1, max_length=200)


class TabelaEstados(_Estrito):
    versao: str = Field(pattern=r'^\d+\.\d+\.\d+$')
    origem: list[Origem] = Field(min_length=1)
    tabela: dict[str, Estado] = Field(min_length=1)


class Aprovacao(_Estrito):
    status: Literal['PENDENTE', 'APROVADO', 'REVOGADO']
    responsavel: str | None
    observacao: str


class PoliticaOperacional(_Estrito):
    schema_version: Literal['1.0']
    id: str
    versao: str = Field(pattern=r'^\d+\.\d+\.\d+$')
    natureza: Literal['politica_operacional']
    aviso: str
    aprovacao: Aprovacao
    regras: list[Regra] = Field(min_length=1)
    estados: TabelaEstados

    @field_validator('regras')
    @classmethod
    def _ids_unicos(cls, regras):
        ids = [r.rule_id for r in regras]
        if len(ids) != len(set(ids)):
            raise ValueError('rule_id duplicado')
        return regras


def _folhas(condicao):
    if condicao is None:
        return []
    if isinstance(condicao, Comparacao):
        return [condicao]
    filhos = condicao.qualquer if isinstance(condicao, Qualquer) else condicao.todas
    return [f for c in filhos for f in _folhas(c)]


def validar(dados: dict) -> PoliticaOperacional:
    """dict já lido -> política validada. Qualquer desvio de schema: ValueError (pydantic.ValidationError)."""
    return PoliticaOperacional.model_validate(dados)


@lru_cache(maxsize=1)
def carregar() -> PoliticaOperacional:
    return validar(json.loads(ARQUIVO.read_text(encoding='utf-8')))


def sha256() -> str:
    return hashlib.sha256(ARQUIVO.read_bytes()).hexdigest()


def versao() -> str:
    return carregar().versao


def referencia_documento() -> str:
    """'id@versao' da política inteira — vai nas métricas de cada chamada ao modelo."""
    return f'{carregar().id}@{carregar().versao}'


def regra(rule_id: str) -> Regra:
    for r in carregar().regras:
        if r.rule_id == rule_id:
            return r
    raise KeyError(rule_id)


def parametro(rule_id: str, nome: str) -> Decimal:
    return regra(rule_id).parametros[nome].decimal


def referencia(rule_id: str) -> str:
    """'rule_id@versao' — o que entra em `regras_aplicadas` do contrato de resposta."""
    r = regra(rule_id)
    return f'{r.rule_id}@{r.versao}'


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = valor if isinstance(valor, Decimal) else Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    return numero if numero.is_finite() else None


def avaliar_condicao(condicao: Condicao, parametros: dict[str, Parametro], indicadores: dict):
    """True/False, ou None quando algum indicador necessário não foi medido (lógica de Kleene).

    `qualquer`: True se alguma folha é True, mesmo com outra None; `todas`: False se alguma é False."""
    if isinstance(condicao, Comparacao):
        valor = _numero(indicadores.get(condicao.indicador))
        if valor is None:
            return None
        return OPERADORES[condicao.operador](valor, parametros[condicao.parametro].decimal)
    filhos = condicao.qualquer if isinstance(condicao, Qualquer) else condicao.todas
    resultados = [avaliar_condicao(c, parametros, indicadores) for c in filhos]
    if isinstance(condicao, Qualquer):
        return True if True in resultados else (None if None in resultados else False)
    return False if False in resultados else (None if None in resultados else True)


def avaliar(rule_id: str, indicadores: dict):
    r = regra(rule_id)
    if r.condicao is None:
        raise ValueError(f'{rule_id} não tem condição executável')
    return avaliar_condicao(r.condicao, r.parametros, indicadores)


def estados() -> dict[str, Estado]:
    return carregar().estados.tabela
