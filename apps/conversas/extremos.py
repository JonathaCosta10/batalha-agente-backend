"""Encaminhamento por extremos no chat: deteção DETERMINÍSTICA por regra, ANTES do modelo.

Pedido do dono via backend-25 (2026-09-27 06:56); contrato publicado pela backend-25 a 2026-09-27 07:30.
Com motivo detetado, o modelo NÃO é chamado: a resposta é o texto fixo da fala do roteiro da 25, lido por `fala_id`
(roteiro.json, estágio "extremo"). Sem a fala no roteiro, usa a constante PROVISORIO daqui.

Envelope (conversas/mensagens/ e conversas/interacao/):
    encaminhamento: null | {destino: "humano"|"seguranca", motivo, fala_id, visivel: false, detectado_por: "regra"|"guard"}

Motivo -> destino:  flerte -> humano (sem alarme) · ameaca -> seguranca · autolesao -> humano (prioridade)
                    · abuso -> humano · extremo_financeiro (consolidação de dívida já existente) -> humano
Prioridade com mais de um motivo: autolesao > ameaca > abuso > flerte > extremo_financeiro.
Registo: o ledger guarda o motivo e o sha256 da mensagem, NUNCA o texto (em autolesao e ameaca isto é obrigatório;
aqui vale para todos os motivos).

Provas negativas (tests/test_conversas_extremos.py): "ameaça de juros", "estou morrendo de gastar", "matar a dívida",
"flertando com o limite do cartão" e frases financeiras normais NÃO disparam.
"""
import hashlib
import re

from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora.visoes import normalizar_texto

PRIORIDADE = ('autolesao', 'ameaca', 'abuso', 'flerte', 'extremo_financeiro')
DESTINO = {'autolesao': 'humano', 'ameaca': 'seguranca', 'abuso': 'humano', 'flerte': 'humano',
           'extremo_financeiro': 'humano'}
FALA_ID = {'autolesao': 'extremo.autolesao', 'ameaca': 'extremo.ameaca', 'abuso': 'extremo.abuso',
           'flerte': 'extremo.flerte', 'extremo_financeiro': 'extremo.encaminhamento_humano'}
# Só usadas se o roteiro não tiver a fala. PROVISORIO: redação a confirmar pelo dono.
PROVISORIO = {
    'autolesao': 'PROVISORIO: Sinto muito que você esteja passando por isso. Você não está só: o CVV atende 24h, de '
                 'graça, no 188. Vou chamar uma pessoa da nossa equipe para falar com você.',
    'ameaca': 'PROVISORIO: Vou encaminhar esta conversa para a equipe de segurança.',
    'abuso': 'PROVISORIO: Quero continuar te ajudando, mas vamos manter o respeito.',
    'flerte': 'PROVISORIO: Sou uma assistente virtual. Posso te ajudar com o seu plano.',
    'extremo_financeiro': 'PROVISORIO: Vou passar esta conversa para uma pessoa da nossa equipe.',
}

_ALVO_FINANCEIRO = (r'(?:a |as |o |os |essa |essas |esse |esses |minha |minhas |meu |meus |de )?'
                    r'(?:divida|dividas|parcela|parcelas|fatura|faturas|conta|contas|emprestimo|emprestimos|juros|'
                    r'saldo|limite|cartao|gasto|gastos|boleto|boletos|financiamento)\b')
REGRAS = {
    'autolesao': re.compile(
        r'\bquero morrer\b|\bvou me matar\b|\bpenso em me matar\b|\bme matar\b(?! de (?:trabalhar|rir|estudar))|'
        r'\btirar (?:a )?(?:minha )?(?:propria )?vida\b|\bacabar com (?:a )?minha vida\b|\bsuicid\w*|'
        r'\bnao quero mais viver\b|\bnao aguento mais viver\b|\bme machucar\b|\bme cortar\b|\bsumir de vez\b|'
        # Ideação indireta (corpus Gemini 2026-09-27 08:57, sessão d9): só formas inequívocas. "cansado de lutar" e
        # "pressão na cabeça" ficam fora: ambíguas, decisão clínica/dono (docs/relatorio-migracao-politica §7).
        r'\b(?:vontade de|queria) (?:sumir|desaparecer)\b(?! com\b)|\b(?:vontade de|queria) morrer\b|'
        r'\bnao queria mais (?:existir|acordar|estar aqui)\b|\bcansad[oa] de viver\b|\bmelhor sem mim\b'),
    'ameaca': re.compile(
        r'\bvou (?:te |lhe )?(?:matar|agredir|espancar|esfaquear|dar um tiro)\b(?! ' + _ALVO_FINANCEIRO + r')|'
        r'\bvou (?:bater|atirar) (?:em|no|na|nele|nela)\b|\b(?:colocar|botar|jogar|explodir) uma bomba\b|'
        r'\bbomba n[oa] (?:banco|agencia)\b|\bvou (?:explodir|invadir|incendiar|queimar) (?:o banco|a agencia|voces)\b|'
        r'\bsei onde (?:voce|voces|o gerente|a gerente|ele|ela) mora\b|\bvoces vao (?:se arrepender|pagar caro)\b|'
        r'\bvou (?:acabar com|pegar) (?:o|a) (?:gerente|atendente)\b'),
    'flerte': re.compile(
        r'\bnamora comigo\b|\bquer namorar\b|\bvamos namorar\b|\bsai comigo\b|\bquer sair comigo\b|'
        r'\b(?:voce|vc) e (?:muito |mto |mt )?(?:linda|lindo|gostosa|gostoso|gata|gato|uma gata|um gato)\b|\bte amo\b|'
        r'\bcasaria (?:facil )?com (?:voce|vc)\b|'
        r'\bestou apaixonad[oa] por voce\b|\bme (?:da|manda) (?:um beijo|seu numero|uma foto)\b|\bcasa comigo\b'),
}
INSULTOS = re.compile(r'\b(?:idiota|burr[oa]|inutil|imbecil|estupid[oa]|otari[oa]|incompetente|vagabund[oa]|'
                      r'desgracad[oa]|lixo|merda|porcaria|fdp|babaca|retardad[oa])\b')
INSULTO_DIRIGIDO = re.compile(r'\bvoce e (?:uma? )?(?:idiota|burr[oa]|inutil|imbecil|estupid[oa]|otari[oa]|'
                              r'incompetente|lixo|babaca)\b|\bsua (?:idiota|burra|inutil|imbecil|estupida|otaria)\b|'
                              r'\bseu (?:idiota|burro|inutil|imbecil|estupido|otario|lixo)\b|'
                              r'\b(?:odeio|detesto) (?:voce|vc|voces)\b')


def motivos(mensagem):
    """Todos os motivos detetados (sem extremo_financeiro, que vem do gatilho de dívida), na ordem de prioridade."""
    norm = normalizar_texto(mensagem or '')
    achados = {m for m, r in REGRAS.items() if r.search(norm)}
    if len(INSULTOS.findall(norm)) >= 2 or INSULTO_DIRIGIDO.search(norm):
        achados.add('abuso')
    return [m for m in PRIORIDADE if m in achados]


def encaminhamento(motivo, detectado_por='regra'):
    return {'destino': DESTINO[motivo], 'motivo': motivo, 'fala_id': FALA_ID[motivo], 'visivel': False,
            'detectado_por': detectado_por}


def detectar(mensagem):
    """-> encaminhamento do motivo de maior prioridade, ou None."""
    achados = motivos(mensagem)
    return encaminhamento(achados[0]) if achados else None


def fala(motivo):
    """-> (texto, fonte). Lê o roteiro a cada chamada (mudança no arquivo vale na chamada seguinte)."""
    try:
        from apps.context_agent_datadriven.views_controle_conversa import carregar_roteiro
        roteiro = carregar_roteiro()
        f = next((f for f in roteiro['falas'] if f['id'] == FALA_ID[motivo]), None)
        if f and isinstance(f.get('texto'), str) and f['texto'].strip():
            return f['texto'], f"roteiro {roteiro.get('versao')} {FALA_ID[motivo]}"
    except Exception:
        pass
    return PROVISORIO[motivo], 'PROVISORIO (fala ausente no roteiro)'


def sha(mensagem):
    return hashlib.sha256((mensagem or '').encode('utf-8')).hexdigest()


def registrar(motivo, mensagem, rota, indice=None, pasta=None):
    """Ledger relatorios/avaliacoes: motivo + sha256 da mensagem. Nunca o texto."""
    from . import interacao_avaliacao as av
    from datetime import datetime
    return av.registrar({'em': datetime.now(av.BRT).isoformat(timespec='seconds'), 'etapa': rota,
                         'encaminhamento': motivo, 'destino': DESTINO[motivo], 'indice': indice,
                         'mensagem_sha256': sha(mensagem), 'origem_resposta': 'encaminhamento', 'aprovado': True,
                         'tentativas': []}, pasta)
