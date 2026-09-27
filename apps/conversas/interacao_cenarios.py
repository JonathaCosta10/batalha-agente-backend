"""Decisões DETERMINÍSTICAS da interação: fluxo por perfil T3 × situação, domínio da pergunta e cenário.

Nada aqui chama o modelo. O Gemini só redige sobre o esqueleto que este módulo escolhe; a mesma entrada dá sempre
o mesmo fluxo/cenário (teste em tests/test_conversas_interacao.py::Deterministico).

    selecionar_fluxo(segmento, situacao, ...)  tabela versionada fluxos_comportamento.json (16 combinações)
    classificar_dominio(mensagem)              'financeiro' | 'fora'  (fora: FORA_DO_CONTEXTO, sem Gemini)
    selecionar_cenario(dados, mensagem)        consolidacao_divida > inclinacao_gasto > financeiro_geral
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora.visoes import normalizar_texto

from . import interacao_dados as dd

ARQ_FLUXOS = Path(__file__).with_name('fluxos_comportamento.json')

# Resposta FIXA fora do contexto financeiro (sem Gemini). Redação PROVISÓRIA: o dono escreveu
# "não faço ideia sabia. é a resposta, i.ai que eu não sei ?" e ainda vai confirmar o texto exato. Única constante.
FORA_DO_CONTEXTO = 'Não faço ideia, sabia? Aí é que eu não sei.'

# Encaminhamento humano da consolidação: texto FIXO anexado pelo servidor (o modelo não o escreve). Sem taxa, sem
# aprovação, sem valor: a oferta existe só por negociação com uma pessoa do banco (RC 8/2023 art. 2 §1º III).
HANDOFF_CONSOLIDACAO = ('Para isso, o caminho é conversar com um especialista do banco: ele avalia com você, numa '
                        'negociação, a consolidação das suas dívidas, e as condições só existem depois dessa análise. '
                        'Quer que eu encaminhe você para esse atendimento humano?')
ACAO_HANDOFF = {'id': 'handoff.consolidacao', 'texto': 'Falar com um especialista', 'etapa_seguinte': None,
                'tipo': 'handoff_humano', 'destino': 'NAO_IMPLEMENTADO: não há rota de atendimento humano no backend'}

FRASE_ALTA = 'Nesses últimos tempos tenho percebido uma leve inclinação a você gastar um pouco mais com {x}'
FRASE_QUEDA = 'Nesses últimos tempos tenho percebido uma leve inclinação a você gastar um pouco menos com {x}'
FRASE_AJUSTE = 'Talvez valha gastar um pouco menos com {x}'

# Domínio: raízes financeiras em texto normalizado (sem acento, minúsculas). "receita", "ganhou", "capital" ficam
# FORA de propósito ("receita de bolo", "quem ganhou o jogo?", "capital da França" -> fora).
FINANCEIRO = re.compile(
    r'\bgast\w*|\bdinheiro\b|\bgrana\b|\bsaldo|\borcament\w*|\bcontas\b|\bminha conta\b|\bdivid\w*|\bdevendo\b|'
    r'\bemprest\w*|\bfinanci\w*|\bfatura\w*|\bcartao\b|\bcredito\b|\bdebito\b|\bjuros?\b|\bparcel\w*|\breserva\b|'
    r'\beconomi\w*|\bpoup\w*|\bsobr\w* (?:de )?dinheiro|\bsobrou\b|\bfaltou\b|\bfalta dinheiro|\bsalario\w*|\brenda\b|'
    r'\bpag(?:ar|uei|amento\w*|o as|ando)\b|\bpix\b|\bboleto\w*|\bbanco\b|\binvest\w*|\bcompromisso\w*|'
    r'\bentrou\b|\bsaiu\b|\bvermelho\b|\bno azul\b|\bcategoria\w*|\bexager\w*|\bapert\w*|\bquitar\b|\bdevo\b|\b50[ /-]?30[ /-]?20\b|\bcust\w*|\bpreco\w*|\breais\b|r\$|\bdespesa\w*|\brecebi\b|\blimite\b|\bcortar\b|'
    r'\bcompras?\b|\bmercado\b|\bconsum\w*|\baluguel\b|\bimposto\w*|\bentradas?\b|\bsaidas?\b|\bmeu mes\b|'
    r'\b(?:este|esse|neste|nesse) mes\b|\bmes passado\b|\bplanejamento\b|\bmeta\b|\bdesafio\b|\bnegocia\w*')
INTENCAO_GASTO = re.compile(r'\bgast\w*|\bcortar\b|\bcorte\b|\beconomi\w*|\breduzir\b|\bonde\b|\bcomo (?:estou|ando|vou)\b|'
                            r'\bhabito\w*|\bcomportamento\b|\bconsum\w*|\bcompras?\b|\bcategoria\w*|\bexager\w*')


@lru_cache(maxsize=1)
def fluxos():
    return json.loads(ARQ_FLUXOS.read_text(encoding='utf-8'))


def _brl(valor):
    from .interacao import brl
    return brl(valor)


def selecionar_fluxo(segmento, situacao, *, janela=None, mes=None, saldo=None, entradas=None, saidas=None,
                     maior_desejo=None):
    """Desde a versão 2026-09-27.2 a situação e os valores são os da MÉDIA mensal da janela (`janela`); `mes` é aceito
    como sinônimo antigo de `janela`."""
    tabela = fluxos()
    seg = segmento if segmento in tabela['fluxos'] else 'NAO_MEDIDO'
    sit = situacao if situacao in tabela['fluxos'][seg] else dd.NAO_MEDIDO
    f = tabela['fluxos'][seg][sit]
    base = f['mensagem_base'].format(janela=janela or mes or 'NAO_MEDIDO', saldo=_brl(saldo), entradas=_brl(entradas),
                                     saidas=_brl(saidas), maior_desejo=maior_desejo or 'a maior categoria de desejos')
    return {'id': f['id'], 'versao': tabela['versao'], 'segmento': seg, 'situacao': sit,
            'proximo_passo': f['proximo_passo'], 'regras': list(f['regras']), 'mensagem_base': base,
            'chave': list(f['chave'])}


def fluxo_de(dados):
    sc, pt3 = dados.get('situacao_conversa') or {}, dados.get('perfil_t3') or {}
    inc = dados.get('inclinacao') or {}
    maior = pt3.get('maior_categoria_discricionaria') or ((inc.get('maior_desejo_recente') or {}).get('subcategoria'))
    return selecionar_fluxo(pt3.get('segmento'), dd.situacao_da_conversa(dados), janela=sc.get('janela'),
                            saldo=sc.get('saldo_medio'), entradas=sc.get('entradas_media'), saidas=sc.get('saidas_media'),
                            maior_desejo=maior)


def classificar_dominio(mensagem):
    return 'financeiro' if FINANCEIRO.search(normalizar_texto(mensagem or '')) else 'fora'


def _pressao(dados):
    seg = (dados.get('perfil_t3') or {}).get('segmento')
    return seg in ('Vulnerável', 'Esbanjador') or dd.situacao_da_conversa(dados) == dd.FALTOU


def gatilho_consolidacao(dados):
    """Dívida relevante medida E pressão (Vulnerável, ou FALTOU na média da janela). Determinístico."""
    div = dados.get('divida') or {}
    seg = (dados.get('perfil_t3') or {}).get('segmento')
    pressao = seg == 'Vulnerável' or dd.situacao_da_conversa(dados) == dd.FALTOU
    return div.get('estado') == 'MEDIDO' and bool(div.get('relevante')) and pressao


def _linha_valor(c, inc):
    return (f": de {inc['recentes']} foram {_brl(c['media_recente'])} por mês, contra {_brl(c['media_janela'])} "
            f"em média de {inc['janela']}.")


def selecionar_cenario(dados, mensagem):
    """-> {cenario, frases_obrigatorias, esqueleto, anexo, motivo, fatos}. Ordem fixa: consolidação > inclinação > geral."""
    if gatilho_consolidacao(dados):
        d = dados['divida']
        janela = (dados.get('media') or {}).get('janela', 'NAO_MEDIDO')
        from .interacao import pct
        just = (f"Pelos seus números, de {janela} saíram em média {_brl(d['divida_mensal_medio'])} por mês com "
                f"empréstimos e juros, {pct(d['pct_da_entrada_media'])} da sua entrada média")
        just += (f", e houve {d['multas_por_atraso_na_janela']} multa(s) por atraso." if d['multas_por_atraso_na_janela'] else '.')
        return {'cenario': 'consolidacao_divida', 'frases_obrigatorias': [HANDOFF_CONSOLIDACAO], 'esqueleto': just,
                'anexo': HANDOFF_CONSOLIDACAO,
                'motivo': f"dívida relevante (empréstimos + juros = {d['pct_da_entrada_media']} % da entrada média, "
                          f"limiar {d['limiar_pct']} %, ou multa por atraso = {d['multas_por_atraso_na_janela']}) e pressão "
                          f"(T3/situação)", 'fatos': d}
    inc = dados.get('inclinacao') or {}
    if inc.get('estado') == 'MEDIDO' and INTENCAO_GASTO.search(normalizar_texto(mensagem or '')):
        frases, esqueleto, fatos = [], None, None
        if inc.get('alta'):
            c = inc['alta']
            frases.append(FRASE_ALTA.format(x=c['subcategoria']))
            esqueleto, fatos = frases[0] + _linha_valor(c, inc), {'tipo': 'alta', **c}
            if _pressao(dados):
                frases.append(FRASE_AJUSTE.format(x=c['subcategoria']))
                esqueleto += ' ' + frases[-1] + '.'
        elif inc.get('queda'):
            c = inc['queda']
            frases.append(FRASE_QUEDA.format(x=c['subcategoria']))
            esqueleto, fatos = frases[0] + _linha_valor(c, inc), {'tipo': 'queda', **c}
        elif _pressao(dados) and inc.get('maior_desejo_recente'):
            c = inc['maior_desejo_recente']
            frases.append(FRASE_AJUSTE.format(x=c['subcategoria']))
            esqueleto = frases[0] + f": de {inc['recentes']} foram {_brl(c['media_recente'])} por mês."
            fatos = {'tipo': 'ajuste', **c}
        if frases:
            return {'cenario': 'inclinacao_gasto', 'frases_obrigatorias': frases, 'esqueleto': esqueleto, 'anexo': None,
                    'motivo': f"limiar {inc['limiares']}; recentes = {inc['recentes']}, janela = {inc['janela']}",
                    'fatos': {**fatos, 'recentes': inc['recentes'], 'janela': inc['janela']}}
    return {'cenario': 'financeiro_geral', 'frases_obrigatorias': [], 'esqueleto': None, 'anexo': None,
            'motivo': 'sem gatilho de dívida; inclinação sem sinal ou pergunta sem intenção de gasto', 'fatos': None}
