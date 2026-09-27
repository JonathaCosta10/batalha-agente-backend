"""Catálogo lexical contextualizado (lexico-v1.json): promessa, aprovação, julgamento e pressão comercial.

Não é uma lista de palavras proibidas: cada achado é avaliado na ORAÇÃO em que aparece.
- negação: um negador ímpar (nao, nunca, nenhum...) até N palavras antes, na mesma oração, torna o achado
  permitido ("Nenhum rendimento é garantido"); expressões que parecem negação mas reforçam a promessa
  ("não se preocupe", "não tem erro") não contam;
- citação: termo entre aspas numa oração com marcador de citação ("desconfie de quem promete 'lucro garantido'")
  é permitido quando a entrada aceita citação.
Normalização antes do casamento: NFKC (letras de largura total etc.), remoção de caracteres invisíveis (soft hyphen,
zero-width), remoção de acentos, minúsculas e espaços colapsados.

Limites conhecidos (medidos nos testes): paráfrase sem termo do catálogo passa; negação sem pontuação separando
("não se assuste o lucro é garantido") pode passar; leetspeak não é tratado. Por isso isto é triagem, e a
decisão de liberar continua exigindo o guard factual e o output_guard.
"""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ARQUIVO = Path(__file__).with_name('lexico-v1.json')
INVISIVEIS = re.compile('[­​-‏⁠-⁤﻿]')
ASPAS = '"\'“”‘’«»„'
TRECHO_CITADO = re.compile(r'["\'“‘«„]([^"\'”’»]{1,120})["\'”’»]')
FIM_DE_ORACAO = re.compile(r'[.;:!?,\n()\[\]—–-]+\s|[.;:!?\n]+$|[.;!?\n]+')


class _Estrito(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class Entrada(_Estrito):
    id: str = Field(pattern=r'^[a-z_]+\.[a-z_]+$')
    categoria: Literal['promessa', 'julgamento', 'pressao_comercial', 'rotulo_interno']
    acao: Literal['bloquear_se_afirmativo', 'bloquear_sempre']
    padroes: list[str] = Field(min_length=1)
    permite_negacao: bool
    permite_citacao: bool
    motivo: str
    exemplos_bloqueados: list[str] = Field(min_length=1)
    exemplos_permitidos: list[str]


class TermosDescritivos(_Estrito):
    termos: list[str]
    condicao: str


class Lexico(_Estrito):
    schema_version: Literal['1.0']
    id: str
    versao: str = Field(pattern=r'^\d+\.\d+\.\d+$')
    natureza: Literal['orientacao_de_comunicacao']
    aviso: str
    negadores: list[str] = Field(min_length=1)
    janela_negacao_palavras: int = Field(ge=1, le=12)
    negacoes_que_nao_negam: list[str]
    marcadores_de_citacao: list[str]
    entradas: list[Entrada] = Field(min_length=1)
    termos_descritivos_permitidos: TermosDescritivos
    linguagem_recomendada_exemplos: list[str]
    linguagem_recomendada_nota: str


def normalizar(texto: str) -> str:
    texto = INVISIVEIS.sub('', unicodedata.normalize('NFKC', texto))
    texto = ''.join(c for c in unicodedata.normalize('NFKD', texto) if not unicodedata.combining(c))
    return re.sub(r'[ \t]+', ' ', texto.casefold())


@lru_cache(maxsize=1)
def carregar() -> Lexico:
    lexico = Lexico.model_validate(json.loads(ARQUIVO.read_text(encoding='utf-8')))
    for entrada in lexico.entradas:
        for padrao in entrada.padroes:
            re.compile(padrao)  # padrão inválido falha no carregamento, não em produção
    return lexico


@lru_cache(maxsize=1)
def _compilados():
    lx = carregar()
    return [(e, re.compile(r'\b(?:' + '|'.join(e.padroes) + r')\b')) for e in lx.entradas]


def _oracoes(texto):
    inicio = 0
    for m in FIM_DE_ORACAO.finditer(texto):
        yield inicio, texto[inicio:m.start()]
        inicio = m.end()
    if inicio < len(texto):
        yield inicio, texto[inicio:]


def _negado(oracao, posicao, lx):
    antes = oracao[:posicao]
    for falsa in lx.negacoes_que_nao_negam:
        antes = antes.replace(falsa, ' ')
    palavras = re.findall(r'[a-z0-9]+', antes)[-lx.janela_negacao_palavras:]
    return sum(p in lx.negadores for p in palavras) % 2 == 1


def _citado(oracao, inicio, fim, lx):
    dentro = any(m.start(1) <= inicio and fim <= m.end(1) for m in TRECHO_CITADO.finditer(oracao))
    return dentro and any(re.search(r'\b' + re.escape(mk) + r'\b', oracao) for mk in lx.marcadores_de_citacao)


def avaliar(texto: str) -> list[dict]:
    """-> um item por achado: {id, categoria, trecho, decisao: BLOQUEADO|PERMITIDO_NEGACAO|PERMITIDO_CITACAO}."""
    lx = carregar()
    achados = []
    for _, oracao in _oracoes(normalizar(texto or '')):
        for entrada, padrao in _compilados():
            for m in padrao.finditer(oracao):
                if entrada.acao == 'bloquear_se_afirmativo' and entrada.permite_negacao and _negado(oracao, m.start(), lx):
                    decisao = 'PERMITIDO_NEGACAO'
                elif entrada.permite_citacao and _citado(oracao, m.start(), m.end(), lx):
                    decisao = 'PERMITIDO_CITACAO'
                else:
                    decisao = 'BLOQUEADO'
                achados.append({'id': entrada.id, 'categoria': entrada.categoria, 'trecho': m.group(0),
                                'decisao': decisao})
    return achados


def bloqueios(texto: str, categorias=None) -> list[dict]:
    return [a for a in avaliar(texto) if a['decisao'] == 'BLOQUEADO'
            and (categorias is None or a['categoria'] in categorias)]


def versao() -> str:
    return carregar().versao
