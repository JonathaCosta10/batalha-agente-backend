"""Base de calibragem de comportamento (comportamento-v1.json): perguntas e respostas-modelo do dono.

Natureza: DADO DE CALIBRAGEM, não política homologada. Cada caso traz diagnóstico, contexto financeiro, pergunta,
raciocínio e resposta ideal para o i.agora. Nada aqui é lido pelo chat em tempo de execução; serve para avaliar e
calibrar (teste offline de schema agora; protocolo LLM de scripts/avaliar_llm.py depois).

Este módulo:
- valida a base com schema estrito (campo desconhecido, contexto ausente, taxa_sobra fora de [-1, 1]: ValueError);
- NÃO corrige dados: `auditar()` devolve achados (duplicados, perfil x contexto, limiares x operacional-v1.json,
  projeções com aritmética errada, produto citado sem catálogo, léxico, marca) para registrar em `achados`/`alerta`.

O schema foi escrito a partir da lista de campos do briefing de 2026-09-27; os tipos de `evidencias`, `renda_media`
e demais campos de texto ficaram tolerantes (texto ou número) até a base real ser conferida contra ele.
"""
import difflib
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from desafio_itau import politica as operacional
from desafio_itau.politica import lexico

ARQUIVO = Path(__file__).with_name('comportamento-v1.json')
PRODUTOS = Path(__file__).with_name('produtos-v1.json')
Numero = Union[int, float, str]


class _Estrito(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class Diagnostico(_Estrito):
    perfil: Union[str, list[str]]
    evidencias: Union[str, list[str]]
    severidade: str = Field(min_length=1)

    @field_validator('perfil')
    @classmethod
    def _perfil_nao_vazio(cls, v):
        if (isinstance(v, str) and not v.strip()) or (isinstance(v, list) and not v):
            raise ValueError('perfil vazio')
        return v


class Contexto(_Estrito):
    renda_media: Numero
    taxa_sobra: Numero
    consumo_flexivel: Numero
    volatilidade_recebimentos: str
    sazonalidade: Union[str, bool]
    reserva: Numero

    @field_validator('taxa_sobra')
    @classmethod
    def _fracao(cls, v):
        d = _decimal(v)
        if d is None or not (Decimal('-1') <= d <= Decimal('1')):
            raise ValueError(f'taxa_sobra deve ser fração em [-1, 1], veio {v!r}')
        return v


class Caso(_Estrito):
    id: int = Field(ge=1)
    bloco: str | None = None
    diagnostico_financeiro: Diagnostico
    tom_calibrado: str = Field(min_length=1)
    perfil_cliente: str = Field(min_length=1)
    contexto_financeiro: Contexto
    intencao_usuario: str = Field(min_length=1)
    entrada_usuario: str = Field(min_length=1)
    raciocinio_de_abordagem: str = Field(min_length=1)
    resposta_ideal_iagora: str = Field(min_length=1)
    acao_sugerida: str = Field(min_length=1)
    gatilho_produto: str = Field(min_length=1)
    compliance_check: Union[str, bool, dict, list]
    alerta: list[str] = Field(default_factory=list)  # achado por caso; o dado original não é alterado


class Fonte(_Estrito):
    descricao: str
    arquivo: str
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    lido_em: str


class Base(_Estrito):
    schema_version: Literal['1.0']
    id: Literal['comportamento-i-agora']
    versao: str = Field(pattern=r'^\d+\.\d+\.\d+$')
    natureza: Literal['dado_de_calibragem']
    status: Literal['NAO_HOMOLOGADO', 'HOMOLOGADO']
    fonte: Fonte
    historico: list[str] = Field(min_length=1)
    achados: list[dict]
    casos: list[Caso] = Field(min_length=1)

    @model_validator(mode='after')
    def _ids_unicos(self):
        ids = [c.id for c in self.casos]
        if len(ids) != len(set(ids)):
            raise ValueError('ids de caso repetidos')
        return self


def _decimal(v):
    if isinstance(v, bool):
        return None
    texto = str(v).strip().replace(',', '.')
    try:
        return Decimal(texto.rstrip('%').strip()) / 100 if texto.endswith('%') else Decimal(texto)
    except (InvalidOperation, ValueError):
        return None


def extrair_casos(texto: str) -> list[dict]:
    """Todo array JSON de objetos com `id` dentro de um texto (a fonte pode ter prosa em volta). Não reescreve dados."""
    dec, casos, i = json.JSONDecoder(), [], 0
    while (i := texto.find('[', i)) != -1:
        try:
            obj, fim = dec.raw_decode(texto, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, list) and obj and all(isinstance(x, dict) and 'id' in x for x in obj):
            casos.extend(obj)
            i = fim
        else:
            i += 1
    return casos


def validar(dados: dict) -> Base:
    return Base.model_validate(dados)


def validar_casos(casos: list) -> list[Caso]:
    return [Caso.model_validate(c) for c in casos]


@lru_cache(maxsize=1)
def carregar() -> Base:
    return validar(json.loads(ARQUIVO.read_text(encoding='utf-8')))


def sha256() -> str:
    return hashlib.sha256(ARQUIVO.read_bytes()).hexdigest()


# ---------------------------------------------------------------- auditoria (achados, nunca correção)

def _norm(texto) -> str:
    return re.sub(r'\s+', ' ', lexico.normalizar(str(texto))).strip()


def _perfis(caso: dict) -> list[str]:
    p = caso['diagnostico_financeiro']['perfil']
    return p if isinstance(p, list) else [p]


def _reais(txt: str) -> Decimal | None:
    t = txt.replace('.', '').replace(',', '.')
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


PROJECAO = re.compile(r'R\$\s?([\d.]+(?:,\d{1,2})?)(?:(?!R\$).){0,80}?R\$\s?([\d.]+(?:,\d{1,2})?)\s*(?:em|ao fim de|depois de|após|apos)\s*(\d{1,3})\s*mes', re.I)
PCT = re.compile(r'(\d{1,3})(?:[.,]\d+)?\s?%')
PALAVRAS_VAZIAS = set('quero posso devo minha minhas meu meus estou tenho fazer como para porque sobre agora ainda '
                      'mais menos isso esse essa qual quais quando onde voce vale pena seria gente'.split())


def auditar(casos: list[dict]) -> tuple[list[dict], dict[int, list[str]]]:
    """-> (achados globais, alertas por id). Heurísticas marcadas como tal: servem de triagem para revisão humana."""
    achados, alertas = [], {c['id']: [] for c in casos}
    limiar = operacional.parametro('t3.limiar_surplus', 'limiar_fracao')
    produtos = json.loads(PRODUTOS.read_text(encoding='utf-8'))

    # 1. duplicados exatos e quase-duplicados (entrada + contexto)
    chaves = {}
    for c in casos:
        chaves.setdefault((_norm(c['entrada_usuario']), json.dumps(c['contexto_financeiro'], sort_keys=True)), []).append(c['id'])
    exatos = [ids for ids in chaves.values() if len(ids) > 1]
    quase = []
    for i, a in enumerate(casos):
        for b in casos[i + 1:]:
            r = difflib.SequenceMatcher(None, _norm(a['entrada_usuario']), _norm(b['entrada_usuario'])).ratio()
            if r >= 0.85 and not any(a['id'] in g and b['id'] in g for g in exatos):
                quase.append([a['id'], b['id'], round(r, 2)])
    for g in exatos:
        for i in g:
            alertas[i].append(f'duplicado_exato:{g}')
    for a, b, r in quase:
        alertas[a].append(f'quase_duplicado:{b}:{r}')
        alertas[b].append(f'quase_duplicado:{a}:{r}')
    achados.append({'tipo': 'duplicados', 'exatos': exatos, 'quase_duplicados': quase,
                    'contagem': {'grupos_exatos': len(exatos), 'pares_quase': len(quase)}})

    # 2. perfil x contexto
    for c in casos:
        perfis = _perfis(c)
        cx = c['contexto_financeiro']
        if len(perfis) > 1:
            alertas[c['id']].append(f'perfil_multiplo:{perfis}')
        if any('volatil' in _norm(p) for p in perfis) and _norm(cx['volatilidade_recebimentos']).startswith('baix'):
            alertas[c['id']].append('perfil_volatilidade_com_volatilidade_baixa')
        sobra = _decimal(cx['taxa_sobra'])
        for p in perfis:
            n = _norm(p)
            if sobra is not None and n.startswith('livre') and sobra < limiar:
                alertas[c['id']].append(f'perfil_livre_com_sobra_{sobra}_abaixo_limiar_{limiar}')
            if sobra is not None and (n.startswith('vulner') or n.startswith('esbanj')) and sobra >= limiar:
                alertas[c['id']].append(f'perfil_{n}_com_sobra_{sobra}_acima_limiar_{limiar}')

    # 3. limiares citados nas respostas x operacional-v1.json
    cita = {}
    for c in casos:
        for m in PCT.finditer(c['resposta_ideal_iagora']):
            cita.setdefault(m.group(1), []).append(c['id'])
    achados.append({'tipo': 'limiares_citados', 'limiar_operacional_t3': str(limiar),
                    'percentuais_citados_ids': {k: sorted(set(v)) for k, v in sorted(cita.items(), key=lambda x: int(x[0]))},
                    'nota': '15% coincide com t3.limiar_surplus (0.15); não há regra "20% = estável" em operacional-v1.json '
                            '(20 só aparece como fatia "futuro" da referência 50/30/20)'})

    # 4. resposta que não toca a pergunta (heurística: nenhuma palavra de conteúdo da pergunta na resposta)
    ignora = []
    for c in casos:
        palavras = {w for w in re.findall(r'[a-z0-9]{5,}', _norm(c['entrada_usuario'])) if w not in PALAVRAS_VAZIAS}
        resp = _norm(c['resposta_ideal_iagora'])
        if palavras and not any(w[:5] in resp for w in palavras):
            ignora.append(c['id'])
            alertas[c['id']].append('resposta_nao_retoma_termo_da_pergunta(heuristica)')
    achados.append({'tipo': 'resposta_ignora_pergunta_heuristica', 'ids': ignora, 'contagem': len(ignora)})

    # 5. projeções R$ x -> R$ y em n meses
    proj = []
    for c in casos:
        for m in PROJECAO.finditer(c['resposta_ideal_iagora']):
            a, b, n = _reais(m.group(1)), _reais(m.group(2)), int(m.group(3))
            ok = a is not None and b is not None and a * n == b
            dados_do_usuario = c['entrada_usuario'] + ' ' + json.dumps(c['contexto_financeiro'], ensure_ascii=False)
            base_no_usuario = bool(re.search(r'(?<![\d.,])' + re.escape(m.group(1)) + r'(?![\d])', dados_do_usuario)
                                   or re.search(r'(?<![\d.,])' + re.escape(m.group(1).replace('.', '')) + r'(?![\d])', dados_do_usuario))
            proj.append({'id': c['id'], 'trecho': m.group(0), 'aritmetica_ok': ok, 'valor_vem_do_usuario': base_no_usuario})
            if not ok:
                alertas[c['id']].append(f'projecao_aritmetica_errada:{a}x{n}!={b}')
            if not base_no_usuario:
                alertas[c['id']].append(f'projecao_com_valor_fora_dos_dados:{m.group(1)}')
    achados.append({'tipo': 'projecoes', 'itens': proj, 'contagem': len(proj),
                    'erradas': [p['id'] for p in proj if not p['aritmetica_ok']],
                    'valor_fora_dos_dados': [p['id'] for p in proj if not p['valor_vem_do_usuario']]})

    # 6. produto citado sem catálogo aprovado
    com_produto = [c['id'] for c in casos if _norm(c['gatilho_produto']) not in ('nenhum', 'nenhuma', '')]
    for i in com_produto:
        alertas[i].append(f'gatilho_produto_sem_catalogo:{produtos["status"]}')
    achados.append({'tipo': 'gatilho_produto', 'status_catalogo': produtos['status'], 'ids': com_produto})

    # 7. léxico
    lex = {}
    for c in casos:
        b = lexico.bloqueios(c['resposta_ideal_iagora'])
        if b:
            lex[c['id']] = sorted({f"{x['id']}:{x['trecho']}" for x in b})
            alertas[c['id']].append(f'lexico:{lex[c["id"]]}')
    achados.append({'tipo': 'lexico', 'versao_lexico': lexico.versao(), 'ids': lex, 'contagem': len(lex)})

    # 8. marca
    marca = [c['id'] for c in casos if re.search(r'\bitau\b', _norm(c['resposta_ideal_iagora'] + ' ' + c['gatilho_produto']))]
    for i in marca:
        alertas[i].append('marca_itau_citada:prototipo_nao_e_canal_oficial')
    achados.append({'tipo': 'marca', 'ids': marca, 'nota': 'comunicacao-v1.json: o protótipo não se apresenta como canal oficial'})

    return achados, {k: v for k, v in alertas.items() if v}
