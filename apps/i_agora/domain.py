"""Situação observada do fluxo de caixa e cálculo explícito das metas; nenhum score de personalidade.

Portado de Frontend/agent_backend/planning/domain.py (2026-09-27). Mudança: o nome gerado por id_usuario
vem do CSV da verdade deste backend (data/usuarios_verdade.csv, coluna `nome`) em vez de nomes_por_id.json.
Conferido na hora do porte: os 1.000 nomes do JSON são iguais aos do CSV (mesma semente, mesmo ficheiro de
origem). Gênero continua sem ser servido.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from uuid import uuid4
import re

MONEY = ('income', 'expenses', 'deliveryCurrent', 'deliveryTarget', 'shoppingCurrent', 'shoppingTarget', 'otherCut',
         'reserveTarget')
CATEGORIES = ('delivery', 'shopping', 'other', 'reserve')
MONTHS = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro',
          'Novembro', 'Dezembro']
NOMES_SELO = {'fonte': 'data/usuarios_verdade.csv', 'natureza': 'nome_gerado',
              'nota': 'nome gerado por semente para o id_usuario; não é dado do cliente. Gênero não é servido.',
              'decidido': 'dono 2026-09-27 10:22 BRT'}


def nomes():
    """{id_usuario: nome gerado}, do CSV da verdade (recarrega se o ficheiro mudar)."""
    from apps.context_agent_datadriven.services import perfil_usuario
    return {k: v['nome'] for k, v in perfil_usuario._carregar()['por_uuid'].items()}


def dec(v):
    if isinstance(v, bool):
        raise ValueError('Valor monetário inválido.')
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        raise ValueError('Valor monetário inválido.') from None
    if not d.is_finite() or d < 0 or d > Decimal('1000000000') or d != d.quantize(Decimal('.01')):
        raise ValueError('Use valores não negativos, com até duas casas decimais.')
    return d


def period_label(p):
    if not re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])', p):
        raise ValueError('Mês de referência inválido.')
    y, m = map(int, p.split('-'))
    return f'{MONTHS[m - 1]} / {y}'


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) - set(MONEY) - {'selected', 'period'} or any(k not in plan for k in MONEY):
        raise ValueError('Plano incompleto ou campos não permitidos.')
    result = {k: float(dec(plan[k])) for k in MONEY}
    selected = plan.get('selected')
    if not isinstance(selected, list) or len(selected) != len(set(selected)) or any(s not in CATEGORIES for s in selected):
        raise ValueError('Categorias inválidas.')
    result['selected'] = selected
    if 'period' in plan:
        period_label(plan['period'])
        result['period'] = plan['period']
    return result


def totals(p):
    d = {k: dec(p[k]) for k in MONEY}
    selected = p['selected']
    delivery = max(Decimal(0), d['deliveryCurrent'] - d['deliveryTarget']) if 'delivery' in selected else Decimal(0)
    shopping = max(Decimal(0), d['shoppingCurrent'] - d['shoppingTarget']) if 'shopping' in selected else Decimal(0)
    other = d['otherCut'] if 'other' in selected else Decimal(0)
    released = delivery + shopping + other
    initial = d['income'] - d['expenses']
    available = initial + released
    reserve = d['reserveTarget'] if 'reserve' in selected else Decimal(0)
    return {k: float(v) for k, v in dict(deliveryCut=delivery, shoppingCut=shopping, otherCut=other, released=released,
                                         initial=initial, available=available, reserve=reserve,
                                         after=available - reserve).items()}


def draft_for_case(baseline, case):
    p = deepcopy(baseline)
    category = case['category']
    amount = dec(case['monthly_amount'])
    if category not in CATEGORIES:
        raise ValueError('Categoria não suportada.')
    field = {'delivery': 'deliveryTarget', 'shopping': 'shoppingTarget', 'other': 'otherCut',
             'reserve': 'reserveTarget'}[category]
    p.update({field: float(amount), 'selected': [category]})
    if category in ('delivery', 'shopping') and amount >= dec(p[category + 'Current']):
        raise ValueError('O alvo de redução precisa ser menor que o gasto observado.')
    if category in ('other', 'reserve') and amount <= 0:
        raise ValueError('Defina uma mudança mensal positiva.')
    remaining = dec(p['expenses']) - dec(p['deliveryCurrent']) - dec(p['shoppingCurrent'])
    if category == 'other' and amount > max(Decimal(0), remaining):
        raise ValueError('A redução supera os outros gastos observados.')
    if category == 'reserve' and amount > max(Decimal(0), dec(p['income']) - dec(p['expenses'])):
        raise ValueError('A reserva não cabe no fluxo observado. Precisamos discutir primeiro como criar espaço.')
    return validate_plan(p)


# Regra do perfil (README do front, seção 12): comparação observada no mês de referência. É a MESMA função que a
# abertura usa (from_snapshot) e que scripts/gerar_situacao_por_usuario.py aplica aos 1.000 ids (sorteio por situação).
SITUACOES = ('fluxo_negativo', 'fluxo_equilibrado', 'sobra_observada')
REGRA_SITUACAO = ('i_agora.domain.situacao_do_mes v1 (README do front, secao 12): saidas > entradas -> fluxo_negativo; '
                  'saidas = entradas -> fluxo_equilibrado; saidas < entradas -> sobra_observada; '
                  'ultimo mes encerrado do cliente, tipo E/S')


def situacao_do_mes(incoming, outgoing):
    incoming, outgoing = dec(incoming), dec(outgoing)
    return 'fluxo_negativo' if outgoing > incoming else 'fluxo_equilibrado' if outgoing == incoming else 'sobra_observada'


def from_snapshot(s):
    # O snapshot normalizado já separa entradas de renda recorrente.
    p = s['reference_month']
    period_label(p)
    y, m = map(int, p.split('-'))
    next_period = f'{y + 1}-01' if m == 12 else f'{y}-{m + 1:02d}'
    incoming, outgoing = dec(s['inflows']), dec(s['outflows'])
    cat = {k.casefold(): dec(v) for k, v in s['categories'].items()}
    delivery = sum((v for k, v in cat.items() if k in ('delivery', 'restaurantes', 'alimentação fora', 'alimentacao fora')),
                   Decimal(0))
    shopping = sum((v for k, v in cat.items() if k in ('lojas e sites', 'compras', 'shopping')), Decimal(0))
    draft = {'income': float(incoming), 'expenses': float(outgoing), 'deliveryCurrent': float(delivery),
             'deliveryTarget': float(delivery), 'shoppingCurrent': float(shopping), 'shoppingTarget': float(shopping),
             'otherCut': 0, 'reserveTarget': 0, 'selected': [], 'period': next_period}
    # Identidade = id_usuario real (a chave da sessão). A tabela não tem nome: o nome é o gerado para esse id.
    ref = str(s['client_ref'])
    nome = nomes().get(ref)
    person = {'id': s.get('index', 1), 'idUsuario': ref, 'nome': nome, 'primeiroNome': nome, 'genero': None,
              'nomeSelo': NOMES_SELO if nome else None, 'plan': deepcopy(draft), 'referenceLabel': period_label(p),
              'planPeriodLabel': period_label(next_period), 'sourceAvailable': True, 'sourceLabel': s['seal']['source']}
    situation = situacao_do_mes(incoming, outgoing)
    return {'planId': str(uuid4()), 'version': 1, 'stage': 'intro', 'draft': draft, 'confirmed': None,
            'confirmedAt': None, 'phraseIndex': 0,
            'profile': {'person': person,
                        'referencePeriod': {'label': period_label(p), 'anomes': int(p.replace('-', '')),
                                            'income': float(incoming), 'expenses': float(outgoing),
                                            'balance': float(incoming - outgoing), 'seal': s['seal']},
                        'planPeriod': {'label': period_label(next_period), 'anomes': int(next_period.replace('-', ''))},
                        'situation': situation, 'arrears': None, 'debt': None, 'recurringIncome': None},
            'snapshot': s, 'totals': totals(draft)}
