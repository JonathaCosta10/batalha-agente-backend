"""Avaliação EM TEMPO DE EXECUÇÃO de cada texto do Gemini numa interação, e o ledger append-only.

Guards determinísticos (cada um com prova negativa em tests/test_conversas_interacao.py):
    numeros      todo R$, % e "N meses" do texto tem fonte nos dados medidos enviados ao modelo
                 (reusa estudos/i_agora/guard.numeros_do_texto: "R$ 1,6 mil" e "1.638 reais" contam)
    situacao     frase com "sobrou"/"faltou"/"no azul"/"no vermelho"... coerente com o sinal do saldo;
                 frase que cita "média" é conferida contra a média da janela, as outras contra o mês;
                 etapa situacional EXIGE dizer a situação; NAO_MEDIDO proíbe afirmar qualquer uma
    nome         (regra do dono 2026-09-27 10:22) nome = `nome_gerado` do MESMO id_usuario (CSV da verdade), presente
                 quando a etapa pede; nome de outro id reprova; gênero nunca é servido: particípio com gênero
                 dirigido à pessoa (preparada/preparado...) reprova
    politica     rules.safe_text (dado sensível, URL, pré-aprovado, taxa) + promessa de resultado +
                 recomendação de produto financeiro + termos proibidos e exclamações do perfil T3
    regra_50_30_20  "necessidades/desejos/futuro ... N %" bate com o medido; o 50/30/20 de referência
                 só vale na frase que o apresenta como referência/meta; o % medido é da MÉDIA da janela e
                 não pode ser atribuído ao mês de referência (".periodo")
    ortografia   palavra comum sem acento (voce, nao, saidas...): saída "achatada" do modelo
    tom_t3       termo exigido do perfil T3 (etapas de ação); sentimento léxico só informativo
    coerencia.sentido  situação e texto no mesmo sentido: "sobrou" + "faltam R$" no mesmo texto reprova; "sobrou"
                 com situação FALTOU (e vice-versa) reprova (regra do dono 2026-09-27 06:22)
    alucinacao.periodo uma só âncora temporal: só a janela da média (+ janeiro de 2026); mês de 2025 isolado reprova

Veredito: qualquer REPROVADO bloqueante reprova. Ledger: relatorios/avaliacoes/<AAAA-MM-DD>.jsonl, uma linha
por resposta servida, sem texto (só sha256), sem chave e sem id_usuario: só o índice do CSV.
"""
import hashlib
import json
import re
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings

from desafio_itau.politica import lexico

from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora import guard as guard_i_agora, t3
from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora.visoes import normalizar_texto

from .interacao_dados import DESEJOS, EQUILIBRIO, FALTOU, FUTURO, NAO_MEDIDO, NECESSIDADES, REFERENCIA_50_30_20, SOBROU
from .rules import safe_text

BRT = ZoneInfo('America/Sao_Paulo')
APROVADO, REPROVADO, NAO_MEDIDO_G = 'APROVADO', 'REPROVADO', 'NAO_MEDIDO'
PASTA_LEDGER = Path(settings.BASE_DIR) / 'relatorios' / 'avaliacoes'
_trava = threading.Lock()

PISTAS = {
    SOBROU: re.compile(r'\bsobr(?:ou|aram|ando|a de|a no mes)\b|\bsaldo (?:ficou )?positivo\b|\bno azul\b|'
                       r'\bterminou positivo\b|\bentrou mais do que saiu\b|\bentradas (?:foram )?maiores\b'),
    FALTOU: re.compile(r'\bfalt(?:ou|aram)\b|\bsaldo (?:ficou )?negativo\b|\bno vermelho\b|\bficou negativo\b|'
                       r'\bgast(?:ou|aram) mais do que (?:entrou|recebeu|ganhou)\b|\bsaiu mais do que entrou\b|'
                       r'\bsaidas (?:foram |ficaram )?maiores\b|\bsaidas superaram\b'),
    # "mais equilibrad(a)" é objetivo/comparativo (convite 50-30-20: "vida financeira mais equilibrada"), não afirma que
    # entradas e saídas empataram; sem a exclusão o texto do roteiro reprovava para SOBROU/FALTOU (503 medido 10:14 BRT).
    EQUILIBRIO: re.compile(r'\bempat(?:ou|e)\b|(?<!\bmais )\bequilibrad[oa]s?\b|\bzero a zero\b'),
}
PROMESSA = re.compile(r'garantid|com certeza (?:vai|voce vai|vai conseguir)|sem risco|lucro certo|'
                      r'resultado certo|(?:vai|voce vai) (?:ficar rica?o?|enriquecer)|100 ?% (?:de )?(?:certeza|seguro)')
PRODUTO = re.compile(r'\b(?:contrat\w*|invist\w*|investir|apliqu\w*|aplicar|abr\w+ (?:um|uma)|adquir\w*|'
                     r'solicit\w*|pe[cç]\w* (?:um|uma)|fa[cç]a (?:um|uma)|tom\w+ (?:um|uma)|recomend\w*|'
                     r'sugir\w*|use (?:o|um|uma|seu))\b[^.!?\n]{0,40}\b(?:emprestimo|credito|cartao|consorcio|'
                     r'capitalizacao|cdb|lci|lca|tesouro|previdencia|seguro|fundo|acoes|cripto|poupanca|'
                     r'cheque especial|consignado|financiamento)\b')
PALAVRA_MEDIA = re.compile(r'\bmedia\b|\bpor mes nos\b|\bnos ultimos\b|\bna janela\b|\bde janeiro a\b')
REFERENCIA_REGRA = re.compile(r'\bregra\b|\breferencia\b|\bmeta\b|\bideal\b|\bsugere\b|\brecomenda\b|\bate\b|'
                              r'\bno maximo\b|\bpelo menos\b|\bpropoe\b|\b50[- ]30[- ]20\b|\bcomo guia\b')
CLASSE_PALAVRAS = {NECESSIDADES: r'necessidade|essencia', DESEJOS: r'desejo', FUTURO: r'futuro|poupanca|reserva'}
RE_MESES = re.compile(r'\b(\d{1,3})\s*mes(?:es)?\b')
# Particípios que o bot dirige à PESSOA ("você está preparada"); "obrigado" (fala do bot) e "pronto" (o plano) ficam fora.
PARTICIPIOS = ('preparad', 'convidad', 'identificad', 'bem-vind', 'animad', 'comprometid', 'decidid', 'desafiad')
NOMES_QUE_SAO_PALAVRAS = {'rosa', 'luz', 'gloria', 'vitoria', 'graca', 'aurora', 'clara', 'flor', 'paz', 'dores',
                          'bela', 'esperanca', 'neves', 'socorro', 'mar', 'celeste', 'serena', 'jade', 'pietra'}


def _c(nome, resultado, detalhe, bloqueante=True):
    return {'nome': nome, 'resultado': resultado, 'detalhe': detalhe, 'bloqueante': bloqueante}


def frases(texto):
    return [f for f in re.split(r'(?<=[.!?])\s+|\n+', texto) if f.strip()]


# ---------------------------------------------------------------- guards

def _numeros_fonte(valores):
    fontes = []
    for v in valores:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            fontes += [float(v), abs(float(v))]
    return fontes


def guard_numeros(texto, valores_medidos, meses_validos=()):
    """Cada R$ / % / 'N meses' do texto precisa de fonte. Constantes de regra (50, 30, 20, 15 %) contam como fonte."""
    fontes = _numeros_fonte(list(valores_medidos) + list(REFERENCIA_50_30_20.values()) + [t3.LIMIAR_SURPLUS * 100])
    saida = []
    for n in guard_i_agora.numeros_do_texto(texto):
        tol = n['tolerancia'] + 1e-9
        fonte = next((f for f in fontes if abs(f - n['valor']) <= tol), None)
        saida.append(_c(f"numeros:{n['bruto']}", APROVADO if fonte is not None else REPROVADO,
                        f'fonte={fonte}' if fonte is not None else 'número sem fonte nos dados medidos'))
    for m in RE_MESES.finditer(normalizar_texto(texto)):
        n = int(m.group(1))
        ok = n in set(meses_validos)
        saida.append(_c(f'numeros:{m.group(0)}', APROVADO if ok else REPROVADO,
                        f'válidos={sorted(set(meses_validos))}'))
    if not saida:
        saida.append(_c('numeros', APROVADO, 'texto sem número'))
    return saida


# Abstenção explícita ("não vou afirmar se sobrou ou faltou"): com NAO_MEDIDO é o aviso honesto, não afirmação.
# Estreito de propósito: "não sobrou" continua sendo afirmação (de falta) e continua reprovado.
ABSTENCAO = re.compile(r'\bnao (vou|vamos|consigo|posso|da para|e possivel) (afirmar|dizer|saber|confirmar)( ainda)? se\b')


def _pistas(frase_norm):
    return {s for s, p in PISTAS.items() if p.search(frase_norm)}


def guard_situacao(texto, situacao_mes, situacao_media=None, exige=False):
    saida, disse_certo = [], False
    for frase in frases(texto):
        norm = normalizar_texto(frase)
        achadas = _pistas(norm)
        if not achadas:
            continue
        esperado = situacao_media if (situacao_media and PALAVRA_MEDIA.search(norm)) else situacao_mes
        if esperado in (None, NAO_MEDIDO):
            if ABSTENCAO.search(norm):
                continue
            saida.append(_c('situacao', REPROVADO, f'afirma {sorted(achadas)} sem dado medido: {frase[:80]!r}'))
            continue
        erradas = achadas - {esperado}
        if erradas:
            saida.append(_c('situacao', REPROVADO, f'medido={esperado}, texto diz {sorted(erradas)}: {frase[:80]!r}'))
        else:
            disse_certo = disse_certo or esperado == situacao_mes
    if exige and situacao_mes not in (None, NAO_MEDIDO) and not disse_certo and not saida:
        saida.append(_c('situacao', REPROVADO, f'etapa exige dizer a situação do mês ({situacao_mes}); o texto não diz'))
    if situacao_mes == NAO_MEDIDO and exige and not saida:
        saida.append(_c('situacao', APROVADO, 'NAO_MEDIDO: texto não afirma sobra nem falta'))
    return saida or [_c('situacao', APROVADO, f'coerente com mês={situacao_mes}, média={situacao_media}')]


FALTA_VALOR = re.compile(r'\bfalt(?:a|am|ou|aram|ando)\b[^.!?\n]{0,40}(?:r\$|\d)')


def guard_coerencia(texto, situacao):
    """Situação e texto no mesmo sentido (regra do dono 06:22; conflito medido pelo front às 06:53).
    Reprova: dizer que sobrou junto com "faltam R$" (sentidos opostos no mesmo texto, ex. bot.confirm), dizer que
    sobrou com situação FALTOU, ou que faltou com situação SOBROU."""
    norm = normalizar_texto(texto)
    sobrou, faltou = PISTAS[SOBROU].search(norm), PISTAS[FALTOU].search(norm)
    falta_valor = FALTA_VALOR.search(norm)
    if sobrou and falta_valor:
        return [_c('coerencia.sentido', REPROVADO, f'diz {sobrou.group(0)!r} e {falta_valor.group(0)!r} no mesmo texto')]
    if situacao == FALTOU and sobrou:
        return [_c('coerencia.sentido', REPROVADO, f'situação FALTOU e o texto diz {sobrou.group(0)!r}')]
    if situacao == SOBROU and (faltou or falta_valor):
        return [_c('coerencia.sentido', REPROVADO, f'situação SOBROU e o texto diz {(faltou or falta_valor).group(0)!r}')]
    return [_c('coerencia.sentido', APROVADO, f'sentido coerente com {situacao}')]


def guard_nome(texto, titular, outros_nomes=(), exige=False):
    """Regra do dono 10:22: o nome vale quando é o `nome_gerado` do MESMO id_usuario (CSV da verdade); nome de outro
    id reprova. Gênero NUNCA é servido: qualquer particípio com gênero dirigido à pessoa reprova."""
    saida = []
    pessoa = (titular or {}).get('pessoa') or ''
    tem = bool(pessoa) and re.search(r'\b' + re.escape(pessoa) + r'\b', texto) is not None
    if exige:
        saida.append(_c('nome.presente', APROVADO if tem else REPROVADO, f'esperado {pessoa!r} (nome_gerado do id)'))
    alheios = sorted({n for n in outros_nomes if n != pessoa and len(n) > 2
                      and normalizar_texto(n) not in NOMES_QUE_SAO_PALAVRAS
                      and re.search(r'\b' + re.escape(n) + r'\b', texto)})
    saida.append(_c('nome.alheio', REPROVADO if alheios else APROVADO, f'nomes de outro id_usuario no texto: {alheios}'))
    norm = normalizar_texto(texto)
    com_genero = [m.group(0) for m in re.finditer(r'\b(?:' + '|'.join(PARTICIPIOS) + r')[ao]s?\b', norm)]
    saida.append(_c('nome.genero', REPROVADO if com_genero else APROVADO,
                    f'gênero NAO_MEDIDO na base; particípios com gênero dirigidos à pessoa: {com_genero}'))
    return saida


def guard_politica(texto, segmento, codigo=None):
    norm = normalizar_texto(texto)
    saida = [_c('politica.safe_text', APROVADO if safe_text(texto, (codigo,) if codigo else ()) else REPROVADO,
                'rules.safe_text: dado sensível, URL, pré-aprovado, taxa ao mês/ano')]
    # Catálogo lexical contextualizado (desafio_itau/politica/lexico-v1.json): "não é garantido" passa.
    achados = lexico.avaliar(texto)
    for nome, categoria in (('politica.promessa', 'promessa'), ('politica.julgamento', 'julgamento'),
                            ('politica.pressao', 'pressao_comercial'), ('politica.rotulo', 'rotulo_interno')):
        bloq = [a['trecho'] for a in achados if a['categoria'] == categoria and a['decisao'] == 'BLOQUEADO']
        saida.append(_c(nome, REPROVADO if bloq else APROVADO, f'achado={bloq[0] if bloq else None}'))
    q = PRODUTO.search(norm)
    saida.append(_c('politica.produto', REPROVADO if q else APROVADO, f'achado={q.group(0) if q else None}'))
    if segmento in t3.PERFIS_DE_RESPOSTA:
        for c in guard_i_agora.verificar_tom(texto, segmento):
            if c['nome'] in ('tom.exclamacoes', 'tom.proibidos'):
                saida.append(_c('politica.' + c['nome'], c['resultado'], c['detalhe']))
    return saida


def guard_50_30_20(texto, regra, mes_nome=None):
    """Frase que liga uma classe a um %: o % é o medido, ou o de referência numa frase de referência."""
    saida = []
    for frase in frases(texto):
        norm = normalizar_texto(frase)
        pcts = [n['valor'] for n in guard_i_agora.numeros_do_texto(frase) if n['tipo'] == 'pct']
        if not pcts:
            continue
        for classe, padrao in CLASSE_PALAVRAS.items():
            if not re.search(padrao, norm):
                continue
            medido = (regra or {}).get(classe, {}).get('pct') if regra else None
            validos = [v for v in (medido,) if v is not None]
            if REFERENCIA_REGRA.search(norm):
                validos.append(REFERENCIA_50_30_20[classe])
            ok = any(abs(p - v) <= 0.55 for p in pcts for v in validos)
            saida.append(_c(f'regra_50_30_20.{classe}', APROVADO if ok else REPROVADO,
                            f'% no texto={pcts}, medido={medido}, referência aceita={REFERENCIA_REGRA.search(norm) is not None}'))
            cita_medido = medido is not None and any(abs(p - medido) <= 0.55 for p in pcts)
            cita_mes = bool(mes_nome) and normalizar_texto(mes_nome.split(' de ')[0]) in norm
            if cita_medido and cita_mes and not PALAVRA_MEDIA.search(norm):
                saida.append(_c('regra_50_30_20.periodo', REPROVADO,
                                f'percentual da MÉDIA da janela atribuído a {mes_nome}: {frase[:80]!r}'))
    return saida or [_c('regra_50_30_20', APROVADO, 'texto não liga classe a percentual')]


# Formas sem acento que não são outra palavra do português: aparecem quando o modelo "achata" a saída. Inclui a
# acentuação obrigatória dos termos do domínio (orçamento, você, necessário, dívida, reserva não leva acento, mês...).
SEM_ACENTO = re.compile(
    r'\b(?:voce|voces|nao|estao|sao|entao|ola|parabens|pagina|saidas?|situacao|situacoes|protecao|organizacao|'
    r'informacao|orcamentos?|tambem|proximos?|proximas?|possivel|historico|referencia|mes|necessari[oa]s?|'
    r'dividas?|credito|creditos|salario|emprestimos?|ate|ja|so|saude|sera|media|medio|analise|numeros?|'
    r'alem|apos|economico|financas|familia|comecar|servico|servicos|negociacao|consolidacao|opcao|opcoes|'
    r'condicoes|decisao|atencao|seguranca|poupanca|previdencia|essencia|habito|habitos|minimo|maximo|periodo|'
    r'ultimos?|ultimas?)\b',
    re.IGNORECASE)
# Nomes de categoria/subcategoria vêm da base SEM acento ("Vestuario e acessorios", "Emprestimos"): o texto pode
# copiá-los assim. Eles são retirados antes da checagem.
from .interacao_dados import CLASSE_50_30_20 as _MAPA  # noqa: E402

NOMES_CATEGORIA = sorted({n for par in _MAPA for n in par if n}, key=len, reverse=True)


def guard_ortografia(texto, isentos=NOMES_CATEGORIA):
    limpo = texto
    for nome in isentos:
        limpo = re.sub(r'\b' + re.escape(nome) + r'\b', ' ', limpo, flags=re.IGNORECASE)
    achados = sorted({m.group(0).lower() for m in SEM_ACENTO.finditer(limpo)})
    return [_c('ortografia', REPROVADO if achados else APROVADO, f'palavras sem acento: {achados}')]


# ---------------------------------------------------------------- fluxo e cenário determinísticos

def guard_fluxo(texto, fluxo, exige):
    """O texto mantém a ação-base do fluxo escolhido por código (um dos termos `chave` da tabela versionada)."""
    if not fluxo:
        return [_c('fluxo', NAO_MEDIDO_G, 'sem fluxo', bloqueante=False)]
    norm = normalizar_texto(texto)
    ok = any(normalizar_texto(k) in norm for k in fluxo['chave'])
    return [_c('fluxo', APROVADO if ok else REPROVADO, f"{fluxo['id']} ({fluxo['proximo_passo']}): chave={fluxo['chave']}",
               bloqueante=exige)]


def guard_cenario(texto, cenario):
    """Cada frase obrigatória do cenário (inclinação com X real, encaminhamento humano) está no texto."""
    if not cenario or not cenario.get('frases_obrigatorias'):
        return [_c('cenario', APROVADO, f"cenário {(cenario or {}).get('cenario')}: sem frase obrigatória")]
    norm = normalizar_texto(texto)
    faltam = [f for f in cenario['frases_obrigatorias'] if normalizar_texto(f).rstrip('.?') not in norm]
    return [_c(f"cenario.{cenario['cenario']}", REPROVADO if faltam else APROVADO, f'faltam={faltam}')]


# ---------------------------------------------------------------- alucinação: fato fora do bloco de contexto
# Regras de "contextualização estruturada" (fontes): docs/context_scoring.md §1 ("não operar com premissas genéricas
# ou alucinações"); prompts/system.liquid ("Use apenas fatos e referências fornecidos", "Não faça cálculos mentais");
# prompts/partials/financial_distinctions.liquid ("Não atribua 15%, 20% ou 50/30/20 a normas"); knowledge/indice.json
# contrato_consulta_proposto.regras ("Sem evidência suficiente, retornar lacuna"); rules.valid_evidence; estudo
# i-agora t3-e-resposta.md §5. Interpretação aplicada: data, categoria, produto ou norma que não está no bloco reprova.

MESES_NORM = ('janeiro', 'fevereiro', 'marco', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro',
              'novembro', 'dezembro')
RE_MES = re.compile(r'\b(' + '|'.join(MESES_NORM) + r')\b')
RE_ANO = re.compile(r'\b(20\d\d)\b')
PRODUTOS = re.compile(r'\b(emprestimos?|credito|cartao|consorcios?|capitalizacao|cdb|lci|lca|tesouro|previdencia|'
                      r'seguros?|fundos?|acoes|cripto\w*|poupanca|cheque especial|consignado|financiamentos?|'
                      r'portabilidade|refinanciamento|investimentos?|consolidacao)\b')
NORMATIVO = re.compile(r'\b(?:bcb|banco central|resolucao|cmn|conselho monetario|norma|lei)\b[^.!?]{0,60}\b'
                       r'(?:exige|exigem|determina|obriga|recomenda|estabelece|manda|preve|impoe)\b|'
                       r'\b(?:exige|determina|obriga|recomenda|estabelece|manda)\w*\b[^.!?]{0,40}\b(?:bcb|banco central|resolucao|cmn)\b')
NEGACAO = re.compile(r'\bnao\b|\bnunca\b|\bnenhum')
# Nomes de categoria que são palavras comuns ("casa", "educação financeira") não entram no guard de categorias.
CATEGORIAS_COMUNS = {'casa', 'compras', 'diversos', 'outros gastos', 'outras contas', 'outros servicos', 'saque',
                     'boleto', 'cheque', 'multa', 'gas', 'celular', 'seguros', 'educacao', 'lazer', 'viagens',
                     'outros emprestimos', 'emprestimos', 'mercado', 'outros', 'veiculos', 'pets'}


def guard_alucinacao(texto, bloco):
    """`bloco`: {meses:[nomes normalizados], anos:[int], categorias:[nomes], texto_permitido:str}. Sem bloco: NAO_MEDIDO."""
    if not bloco:
        return [_c('alucinacao', NAO_MEDIDO_G, 'sem bloco de contexto', bloqueante=False)]
    norm = normalizar_texto(texto)
    permitido = normalizar_texto(bloco.get('texto_permitido', ''))
    saida = []
    meses_fora = sorted({m for m in RE_MES.findall(norm) if m not in set(bloco.get('meses', ()))})
    anos_fora = sorted({int(a) for a in RE_ANO.findall(norm) if int(a) not in set(bloco.get('anos', ()))})
    saida.append(_c('alucinacao.datas', REPROVADO if (meses_fora or anos_fora) else APROVADO,
                    f'meses fora do bloco={meses_fora}, anos fora={anos_fora}'))
    citaveis = {normalizar_texto(c) for c in bloco.get('categorias', ())}
    conhecidas = {normalizar_texto(n) for n in NOMES_CATEGORIA} - CATEGORIAS_COMUNS
    fora = sorted(c for c in conhecidas if re.search(r'\b' + re.escape(c) + r'\b', norm) and c not in citaveis)
    saida.append(_c('alucinacao.categorias', REPROVADO if fora else APROVADO, f'categorias fora do bloco={fora}'))
    prods = sorted({p for p in PRODUTOS.findall(norm) if not re.search(r'\b' + re.escape(p) + r'\b', permitido)})
    saida.append(_c('alucinacao.produto', REPROVADO if prods else APROVADO, f'produtos fora do bloco={prods}'))
    normas = [f for f in frases(norm) if NORMATIVO.search(f) and not NEGACAO.search(f)]
    saida.append(_c('alucinacao.normativo', REPROVADO if normas else APROVADO,
                    f'atribui exigência à norma: {[f[:80] for f in normas]}'))
    return saida


RE_JANEIRO_PLANO = re.compile(r'\bjaneiro\b(?! de 20\d\d)')


def guard_periodo(texto, periodos):
    """Uma só âncora temporal por conversa: só a janela da média (e janeiro de 2026, o mês do plano; em turno livre com
    inclinação, os períodos da frase do cenário). Um mês de 2025 citado isolado ("novembro de 2025") reprova."""
    if periodos is None:
        return [_c('alucinacao.periodo', NAO_MEDIDO_G, 'sem âncora temporal no contexto', bloqueante=False)]
    norm = normalizar_texto(texto)
    for p in sorted((normalizar_texto(p) for p in periodos if p), key=len, reverse=True):
        norm = norm.replace(p, ' ')
    norm = RE_JANEIRO_PLANO.sub(' ', norm)
    soltos = sorted(set(RE_MES.findall(norm)))
    return [_c('alucinacao.periodo', REPROVADO if soltos else APROVADO,
               f'meses fora da âncora {list(periodos)}: {soltos}')]


def guard_tom(texto, segmento, exige):
    if segmento not in t3.PERFIS_DE_RESPOSTA:
        return [_c('tom_t3', NAO_MEDIDO_G, f'segmento {segmento!r}: sem perfil de tom', bloqueante=False)]
    saida = []
    for c in guard_i_agora.verificar_tom(texto, segmento):
        if c['nome'] == 'tom.exigidos':
            saida.append(_c('tom_t3.exigidos', c['resultado'], c['detalhe'], bloqueante=exige))
        elif c['nome'] == 'sentimento':
            saida.append(_c('tom_t3.sentimento', c['resultado'], c['detalhe'], bloqueante=False))
    return saida


def avaliar(texto, *, titular, contexto, etapa, outros_nomes=()):
    """Roda todos os guards. `contexto`: situacao, situacao_media, segmento, valores, meses_validos, regra e, quando
    houver, fluxo, cenario (com `anexo` fixo do servidor, isento de politica/alucinação) e bloco (alucinação)."""
    cenario = contexto.get('cenario') or {}
    proprio = texto.replace(cenario['anexo'], ' ') if cenario.get('anexo') else texto  # o que o modelo escreveu
    checagens = (guard_numeros(texto, contexto['valores'], contexto.get('meses_validos', ()))
                 + guard_situacao(texto, contexto['situacao'], contexto.get('situacao_media'), etapa.get('exige_situacao', False))
                 + guard_coerencia(proprio, contexto['situacao'])
                 + guard_periodo(proprio, (contexto.get('bloco') or {}).get('periodos_permitidos'))
                 + guard_nome(texto, titular, outros_nomes, etapa.get('exige_nome', False))
                 + guard_politica(proprio, contexto.get('segmento'), titular.get('codigo'))
                 + guard_50_30_20(texto, contexto.get('regra'), contexto.get('mes_nome'))
                 + guard_ortografia(texto)
                 + guard_tom(texto, contexto.get('segmento'), etapa.get('exige_tom', False))
                 + guard_fluxo(texto, contexto.get('fluxo'), etapa.get('exige_fluxo', False))
                 + guard_cenario(texto, cenario)
                 + guard_alucinacao(proprio, contexto.get('bloco')))
    reprovados = sorted({c['nome'].split(':')[0] for c in checagens if c['bloqueante'] and c['resultado'] == REPROVADO})
    return {'aprovado': not reprovados, 'reprovados': reprovados, 'checagens': checagens}


# ---------------------------------------------------------------- ledger

def registrar(linha, pasta=None):
    """Append-only. Recusa linha com texto, UUID ou chave (prova negativa nos testes)."""
    bruto = json.dumps(linha, ensure_ascii=False, sort_keys=True)
    if re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|AIza[\w-]{20,}', bruto) or 'texto' in linha:
        raise ValueError('Ledger recusa UUID, chave ou texto da resposta')
    pasta = Path(pasta or PASTA_LEDGER)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{datetime.now(BRT):%Y-%m-%d}.jsonl"
    with _trava, arquivo.open('a', encoding='utf-8') as saida:
        saida.write(bruto + '\n')
    return arquivo


def sha(texto):
    return hashlib.sha256((texto or '').encode('utf-8')).hexdigest()


def _percentil(valores, p):
    if not valores:
        return None
    v = sorted(valores)
    k = (len(v) - 1) * p / 100
    i = int(k)
    return round(v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * (k - i), 1)


def resumo(pasta=None, data=None):
    pasta = Path(pasta or PASTA_LEDGER)
    arquivos = sorted(pasta.glob(f'{data}.jsonl' if data else '*.jsonl')) if pasta.exists() else []
    linhas = []
    for arq in arquivos:
        for bruta in arq.read_text(encoding='utf-8').splitlines():
            if bruta.strip():
                linhas.append(json.loads(bruta))
    tentativas = [t for l in linhas for t in l.get('tentativas', [])]
    do_modelo = [t for t in tentativas if t.get('latencia_ms') is not None]
    por_guard, por_modelo, por_etapa, por_origem = {}, {}, {}, {}
    for t in tentativas:
        for g in t.get('reprovados', []):
            por_guard[g] = por_guard.get(g, 0) + 1
        m = por_modelo.setdefault(t['modelo'], {'tentativas': 0, 'aprovadas': 0, 'erros_provedor': 0})
        m['tentativas'] += 1
        m['aprovadas'] += bool(t.get('aprovado'))
        m['erros_provedor'] += bool(t.get('erro'))
    for l in linhas:
        e = por_etapa.setdefault(l['etapa'], {'respostas': 0, 'aprovadas': 0})
        e['respostas'] += 1
        e['aprovadas'] += bool(l.get('aprovado'))
        por_origem[l['origem_resposta']] = por_origem.get(l['origem_resposta'], 0) + 1
    avaliadas = [t for t in tentativas if not t.get('erro')]
    lat = [t['latencia_ms'] for t in do_modelo]
    return {
        'fonte': str(pasta.relative_to(settings.BASE_DIR)) if pasta.is_relative_to(settings.BASE_DIR) else str(pasta),
        'arquivos': [a.name for a in arquivos],
        'respostas': len(linhas),
        'respostas_aprovadas': sum(bool(l.get('aprovado')) for l in linhas),
        'taxa_aprovacao_respostas': round(sum(bool(l.get('aprovado')) for l in linhas) / len(linhas), 3) if linhas else NAO_MEDIDO,
        'tentativas_do_modelo': len(tentativas),
        'taxa_aprovacao_tentativas': round(sum(bool(t.get('aprovado')) for t in avaliadas) / len(avaliadas), 3) if avaliadas else NAO_MEDIDO,
        'latencia_ms': {'p50': _percentil(lat, 50), 'p95': _percentil(lat, 95), 'n': len(lat)} if lat else NAO_MEDIDO,
        'reprovacoes_por_guard': dict(sorted(por_guard.items(), key=lambda kv: -kv[1])),
        'por_modelo': por_modelo, 'por_etapa': por_etapa, 'por_origem': por_origem,
        'gerado_em': datetime.now(BRT).isoformat(timespec='seconds'),
    }
