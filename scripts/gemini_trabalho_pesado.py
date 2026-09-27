"""O Gemini faz o trabalho pesado (gerar variedade); o código determinístico decide e é medido.

Uso (da raiz deste repo, PYTHONPATH=. e DJANGO_SETTINGS_MODULE=desafio_itau.settings):
    python scripts/gemini_trabalho_pesado.py corpus  --max-chamadas 4   # Parte A: gera o corpus (rede)
    python scripts/gemini_trabalho_pesado.py medir   --corpus <jsonl>   # Parte A: classificadores (SEM rede)
    python scripts/gemini_trabalho_pesado.py estabilidade --n 3 --max-chamadas 6   # Parte B (rede)

Tudo o que chama a rede passa por `Orcamento`, que conta cada POST (inclusive 429/erro) e recusa passar do teto.
Qualquer 429/erro fica registado como NAO_MEDIDO: nenhum número é inventado.
Saídas: datasets/corpus-intencao-gemini-<AAAA-MM-DDTHHMM>.jsonl (append-only) e
relatorios/gemini-deterministico/<AAAA-MM-DDTHHMM>.json. Horas em BRT (America/Sao_Paulo).
"""
import argparse
import hashlib
import json
import re
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
BRT = ZoneInfo('America/Sao_Paulo')
PASTA_CORPUS = RAIZ / 'datasets'
PASTA_RELATORIO = RAIZ / 'relatorios' / 'gemini-deterministico'
MODELO = 'gemini-3.5-flash-lite'  # gemini-flash-latest dá 429 o dia todo (2026-09-27)
ROTULOS = ('inclinacao_gasto', 'consolidacao_divida', 'financeiro_geral', 'fora_do_contexto', 'extremo')


def agora():
    return datetime.now(BRT)


def sha(texto):
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


def django_setup():
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'desafio_itau.settings')
    import django
    django.setup()


# ------------------------------------------------------------------ classificadores determinísticos (SEM rede)

def classificar(texto):
    """Composição, na ordem de interacao.interagir, dos classificadores que só leem o TEXTO:
    extremos.detectar -> 'extremo'; classificar_dominio == 'fora' -> 'fora_do_contexto';
    INTENCAO_GASTO -> 'inclinacao_gasto'; senão 'financeiro_geral'.
    consolidacao_divida NÃO sai do texto: é decidida pelos DADOS (gatilho_consolidacao). Para esse rótulo o acerto
    é 'domínio financeiro, sem extremo' (qualquer das duas saídas financeiras)."""
    from apps.conversas import extremos, interacao_cenarios as cn
    from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora.visoes import normalizar_texto
    enc = extremos.detectar(texto)
    if enc:
        return 'extremo', {'extremo': enc['motivo'], 'dominio': None, 'intencao_gasto': None}
    dominio = cn.classificar_dominio(texto)
    intencao = bool(cn.INTENCAO_GASTO.search(normalizar_texto(texto)))
    if dominio == 'fora':
        return 'fora_do_contexto', {'extremo': None, 'dominio': dominio, 'intencao_gasto': intencao}
    return ('inclinacao_gasto' if intencao else 'financeiro_geral'), \
        {'extremo': None, 'dominio': dominio, 'intencao_gasto': intencao}


def acertou(esperado, previsto):
    if esperado == 'consolidacao_divida':
        return previsto in ('inclinacao_gasto', 'financeiro_geral')
    return esperado == previsto


def medir(linhas):
    """-> {acerto_por_rotulo, matriz, erradas}. `linhas` = registos do corpus (dicts com rotulo_esperado e texto)."""
    matriz = defaultdict(Counter)
    acerto, total, erradas = Counter(), Counter(), []
    for l in linhas:
        previsto, det = classificar(l['texto'])
        esp = l['rotulo_esperado']
        matriz[esp][previsto] += 1
        total[esp] += 1
        if acertou(esp, previsto):
            acerto[esp] += 1
        else:
            erradas.append({'id': l['id'], 'texto': l['texto'], 'esperado': esp, 'previsto': previsto, **det})
    por = {r: {'acertos': acerto[r], 'total': total[r],
               'pct': round(100 * acerto[r] / total[r], 1) if total[r] else None} for r in ROTULOS}
    return {'acerto_por_rotulo': por, 'matriz': {k: dict(v) for k, v in matriz.items()}, 'erradas': erradas}


# ------------------------------------------------------------------ orçamento de rede

class Orcamento:
    def __init__(self, maximo):
        self.maximo, self.chamadas = maximo, []

    def transporte(self, modelo, corpo):
        from apps.conversas import gateway
        if len(self.chamadas) >= self.maximo:
            raise RuntimeError('orcamento local esgotado (nenhuma chamada feita)')
        registo = {'modelo': modelo, 'em': agora().isoformat(timespec='seconds'), 'http_status': None, 'erro': None}
        self.chamadas.append(registo)
        inicio = time.monotonic()
        try:
            resposta = gateway.transporte_http(modelo, corpo)
            registo['http_status'] = 200
            return resposta
        except Exception as erro:
            registo['http_status'] = getattr(erro, 'code', None)
            registo['erro'] = type(erro).__name__
            raise
        finally:
            registo['latencia_ms'] = round((time.monotonic() - inicio) * 1000)

    def resumo(self):
        por = defaultdict(Counter)
        for c in self.chamadas:
            por[c['modelo']]['chamadas'] += 1
            por[c['modelo']][f"http_{c['http_status']}"] += 1
        return {m: dict(v) for m, v in por.items()}


# ------------------------------------------------------------------ Parte A: corpus

INSTRUCAO_CORPUS = """Você gera dados de TESTE para um classificador de intenção de um assistente financeiro de um banco brasileiro.
Escreva frases realistas, como clientes brasileiros digitariam no chat do app (linguagem coloquial, algumas com erros
de digitação, gírias, sem acento às vezes, curtas e longas). Varie o vocabulário: NÃO repita as mesmas palavras-chave.
Rótulos:
- inclinacao_gasto: a pessoa quer saber onde/como está gastando, se está exagerando, onde cortar, hábitos de consumo.
- consolidacao_divida: a pessoa fala de dívidas, empréstimos, juros, parcelas atrasadas, quer juntar/renegociar/sair das dívidas.
- financeiro_geral: outras perguntas sobre a própria vida financeira (saldo, quanto entrou, reserva, planejamento, salário), sem foco em gasto nem dívida.
- fora_do_contexto: assuntos sem relação com finanças pessoais (clima, futebol, receitas, curiosidades, tecnologia).
- extremo: mensagens de flerte com a assistente ou insulto leve a ela; no máximo 2 frases INDIRETAS e sóbrias de
  sofrimento emocional grave (sem método, sem detalhe, sem conteúdo gráfico). Nada de ameaça a terceiros.
Gere {n} frases por rótulo. Responda só o JSON do schema."""

SCHEMA_CORPUS = {'type': 'object', 'properties': {r: {'type': 'array', 'items': {'type': 'string'}} for r in ROTULOS},
                 'required': list(ROTULOS)}


def gerar_corpus(orc, n=12, max_tokens=6000):
    from apps.conversas import gateway
    gateway.TIMEOUT_SEGUNDOS = 90  # só neste processo: 60 frases numa resposta passam dos 15 s padrão
    instrucao = INSTRUCAO_CORPUS.format(n=n)
    pedido = f'Gere o corpus agora: {n} frases para cada um dos {len(ROTULOS)} rótulos.'
    corpo = gateway.corpo_pedido(instrucao, pedido, SCHEMA_CORPUS, max_tokens)
    prompt_sha = sha(instrucao + '\n' + pedido)
    ts = agora()
    try:
        resposta = orc.transporte(MODELO, corpo)
        texto = gateway.validated_text(resposta['candidates'][0])
        dados = json.loads(texto)
    except Exception as erro:
        return None, {'estado': 'NAO_MEDIDO', 'erro': f'{type(erro).__name__}: {getattr(erro, "code", "") or erro}'}
    arq = PASTA_CORPUS / f'corpus-intencao-gemini-{ts:%Y-%m-%dT%H%M}.jsonl'
    selo = {'modelo': MODELO, 'model_version': resposta.get('modelVersion'), 'gerado_em': ts.isoformat(timespec='seconds'),
            'prompt_sha256': prompt_sha, 'resposta_sha256': sha(texto), 'uso_tokens': resposta.get('usageMetadata')}
    linhas, vistos = [], set()
    for r in ROTULOS:
        for i, frase in enumerate(dados.get(r) or []):
            frase = (frase or '').strip()
            if not frase or frase.lower() in vistos:
                continue
            vistos.add(frase.lower())
            linhas.append({'id': f'{r}-{i + 1:02d}', 'rotulo_esperado': r, 'texto': frase, **selo})
    with arq.open('a', encoding='utf-8') as f:  # append-only
        for l in linhas:
            f.write(json.dumps(l, ensure_ascii=False) + '\n')
    return arq, {'estado': 'MEDIDO', **selo, 'frases': len(linhas),
                 'por_rotulo': dict(Counter(l['rotulo_esperado'] for l in linhas))}


def ler_corpus(arq):
    return [json.loads(l) for l in Path(arq).read_text(encoding='utf-8').splitlines() if l.strip()]


# ------------------------------------------------------------------ Parte B: estabilidade

MARIA = '00108ccd-699c-453a-a9f9-a66aad6e03e5'
TITULAR = {'codigo': MARIA, 'pessoa': 'Maria', 'genero': 'F', 'indice': 1}
SELO_FALSO = {'fonte': 'SINTETICO (fonte falsa em fontes=, sem BigQuery)', 'natureza_da_base': 'sintetica',
              'medido_em': '2026-09-27T00:00:00-03:00', 'jobs': {'mensal_50_30_20': 'falso'}, 'data_corte': '2025-12-22'}
PERFIL_FALSO = {
    'usuario': {'indice': 1, 'id_usuario': MARIA}, 'data_corte': '2025-12-22',
    'resumo': {'segmento_t3': 'Vulnerável', 'inflow_mensal': 8828.12, 'outflow_mensal': 10790.43,
               'surplus_mensal': -1962.31, 'taxa_surplus_pct': -22.23, 'meses_na_janela': 11},
    'visoes': {'perfil_t3': {'essencial_mensal': 3983.87, 'compromisso_mensal': 5006.58, 'discricionario_mensal': 1664.13},
               'discricionario': {'maior_categoria_discricionaria': 'Lojas e sites'}},
    'selo': SELO_FALSO}


def _mes(anomes, e, s):
    return {'anomes': anomes, 'entradas': e, 'saidas': s, 'necessidades': 6000.0, 'desejos': 1000.0,
            'futuro_programado': 10.0, 'fora_da_regra': 1500.0, 'saidas_sem_classe': 0}


LINHAS_FALSAS = [_mes(202500 + m, 9800.0, 8000.0) for m in range(1, 11)] + [_mes(202511, 8596.41, 9895.85)]


def fontes_falsas():
    from copy import deepcopy
    return {'perfil': lambda c: deepcopy(PERFIL_FALSO), 'mensal': lambda c: (deepcopy(LINHAS_FALSAS), SELO_FALSO),
            'proposta': lambda c: None, 'subcategorias': lambda c: None}


NUM = re.compile(r'R\$\s?[\d.]+,\d{2}|\d+(?:,\d+)?\s?%')


def _valores(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _valores(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _valores(v)
    elif isinstance(obj, str):
        yield obj


def numeros_citados(texto):
    return [re.sub(r'\s', '', n) for n in NUM.findall(texto or '')]


def estabilidade(orc, etapa='intro.carrossel.1', n=3):
    from apps.conversas import interacao
    execucoes = []
    pasta = tempfile.mkdtemp()
    for i in range(n):
        if len(orc.chamadas) >= orc.maximo:
            execucoes.append({'execucao': i + 1, 'estado': 'NAO_MEDIDO', 'motivo': 'orçamento de chamadas esgotado'})
            continue
        if any(c['http_status'] == 429 for c in orc.chamadas):  # cota do dia: não gastar mais pedidos
            execucoes.append({'execucao': i + 1, 'estado': 'NAO_MEDIDO', 'motivo': 'não chamado: 429 anterior'})
            continue
        antes = len(orc.chamadas)
        inicio = time.perf_counter()
        try:
            c = interacao.interagir(TITULAR, etapa, fontes=fontes_falsas(), transporte=orc.transporte, modelos=(MODELO,),
                                    budget=5, pasta_ledger=pasta, outros_nomes=[], guard_entrada_modelo=False)
        except interacao.SemResposta as e:
            c = e.corpo
        permitidos = {re.sub(r'\s', '', v) for v in _valores(interacao.formatados(c['dados'])) if NUM.fullmatch(v.strip() or 'x')}
        citados = numeros_citados(c['texto'])
        a = c['avaliacao']
        t = (a['tentativas'] or [{}])[0]
        execucoes.append({
            'execucao': i + 1, 'estado': 'MEDIDO' if c['origem_resposta'] == 'modelo' else 'NAO_MEDIDO',
            'chamadas_http': len(orc.chamadas) - antes, 'origem_resposta': c['origem_resposta'],
            'aprovado': c['aprovado'], 'reprovados': a['reprovados'] or t.get('reprovados'),
            'erro_tentativa': t.get('erro'), 'http_status': t.get('http_status'),
            'texto_sha256': sha(c['texto'] or ''), 'texto': c['texto'],
            'latencia_ms': a['latencia_ms'] or t.get('latencia_ms'), 'tokens': a['tokens'] or t.get('tokens'),
            'model_version': a['model_version'], 'tempo_total_ms': round((time.perf_counter() - inicio) * 1000),
            'fluxo': c['fluxo']['id'], 'situacao': c['situacao'], 'perfil_t3': c['perfil_t3'],
            'cenario': (c['cenario'] or {}).get('cenario'),
            'numeros_citados': citados, 'numeros_fora_de_dados': [x for x in citados if x not in permitidos],
            'decisao_sha256': sha(json.dumps({'fluxo': c['fluxo'], 'situacao': c['situacao'], 'perfil_t3': c['perfil_t3'],
                                              'dados': interacao.formatados(c['dados'])}, sort_keys=True, ensure_ascii=False)),
        })
    medidas = [e for e in execucoes if e['estado'] == 'MEDIDO']
    return {
        'etapa': etapa, 'dados': 'sintéticos fixos (PERFIL_FALSO + LINHAS_FALSAS), fontes=, sem BigQuery',
        'guard_entrada_modelo': False, 'execucoes': execucoes,
        'n_pedidas': n, 'n_medidas': len(medidas),
        'textos_distintos': len({e['texto_sha256'] for e in medidas}) if medidas else 'NAO_MEDIDO',
        'aprovadas': sum(e['aprovado'] for e in medidas) if medidas else 'NAO_MEDIDO',
        'decisoes_distintas': len({e['decisao_sha256'] for e in execucoes if 'decisao_sha256' in e}),
        'conjuntos_de_numeros_distintos': len({tuple(sorted(e['numeros_citados'])) for e in medidas}) if medidas else 'NAO_MEDIDO',
        'numeros_sempre_em_dados': all(not e['numeros_fora_de_dados'] for e in medidas) if medidas else 'NAO_MEDIDO',
    }


# ------------------------------------------------------------------ CLI

def relatorio(nome, conteudo):
    PASTA_RELATORIO.mkdir(parents=True, exist_ok=True)
    arq = PASTA_RELATORIO / nome
    atual = json.loads(arq.read_text(encoding='utf-8')) if arq.exists() else {}
    atual.update(conteudo)
    arq.write_text(json.dumps(atual, ensure_ascii=False, indent=2), encoding='utf-8')
    return arq


def main():
    p = argparse.ArgumentParser()
    p.add_argument('parte', choices=('corpus', 'medir', 'estabilidade'))
    p.add_argument('--max-chamadas', type=int, default=0)
    p.add_argument('--corpus')
    p.add_argument('--relatorio', help='nome do relatório a completar (AAAA-MM-DDTHHMM.json)')
    p.add_argument('--n', type=int, default=3)
    p.add_argument('--etapa', default='intro.carrossel.1')
    a = p.parse_args()
    django_setup()
    nome = a.relatorio or f'{agora():%Y-%m-%dT%H%M}.json'
    orc = Orcamento(a.max_chamadas)
    if a.parte == 'corpus':
        arq, info = gerar_corpus(orc)
        out = {'parte_a_corpus': {**info, 'arquivo': str(arq.relative_to(RAIZ)) if arq else None,
                                  'chamadas': orc.chamadas, 'chamadas_por_modelo': orc.resumo()}}
    elif a.parte == 'medir':
        linhas = ler_corpus(a.corpus)
        out = {'parte_a_medicao': {'corpus': a.corpus, 'frases': len(linhas), 'medido_em': agora().isoformat(timespec='seconds'),
                                   'rede': 'nenhuma', **medir(linhas)}}
    else:
        r = estabilidade(orc, a.etapa, a.n)
        out = {'parte_b_estabilidade': {**r, 'medido_em': agora().isoformat(timespec='seconds'),
                                        'chamadas': orc.chamadas, 'chamadas_por_modelo': orc.resumo()}}
    arq = relatorio(nome, out)
    print(json.dumps({'relatorio': str(arq.relative_to(RAIZ)), **out}, ensure_ascii=False, indent=1)[:12000])


if __name__ == '__main__':
    main()
