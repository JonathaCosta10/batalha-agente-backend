"""Abertura proativa com base: diz o perfil que a base atribuiu, a aritmética observada e UMA pergunta.

Portado de Frontend/agent_backend/planning/opening.py (2026-09-27), sem mudança de texto.
"""
from apps.conversas.projection import brl

from .domain import dec, period_label

# Nomes das situações observadas calculadas em domain.py; a regra está no README do front, seção 12.
PERFIL = {'fluxo_negativo': 'saídas acima das entradas', 'fluxo_equilibrado': 'entradas e saídas equilibradas',
          'sobra_observada': 'com sobra no mês'}
README_SECAO = '12'


def profile_sentence(state):
    situation = (state.get('profile') or {}).get('situation')
    nome = PERFIL.get(situation)
    if not nome:
        return ''
    return (f'Na nossa base, seu perfil foi considerado "{nome}". O motivo e a modelagem estão explicados '
            f'na seção {README_SECAO} do README (Como o perfil é considerado).\n\n')


def guided_opening(state):
    if state.get('confirmed'):
        return {'phase': 'review_confirmed',
                'message': 'Seu plano aprovado continua salvo. Vamos conferir se ele está funcionando na prática: '
                           'a ação combinada está cabendo na sua rotina ou surgiu algum obstáculo?',
                'focus': None}
    snap = state['snapshot']
    period = snap['reference_month']
    label = period_label(period).lower().replace(' / ', ' de ')
    incoming, outgoing = dec(snap['inflows']), dec(snap['outflows'])
    if outgoing > incoming:
        observation = (f'Olhando os dados de {label}, suas saídas ficaram {brl(str(outgoing - incoming))} acima das '
                       'entradas. Vamos entender o que contribuiu para essa diferença antes de pensar em um ajuste.')
    elif outgoing < incoming:
        observation = (f'Em {label}, suas saídas foram de {brl(str(outgoing))}, ficando {brl(str(incoming - outgoing))} '
                       'abaixo das entradas. Vamos entender onde existe espaço para organizar seu próximo passo.')
    else:
        observation = (f'Em {label}, entradas e saídas ficaram no mesmo valor: {brl(str(outgoing))}. '
                       'Vamos entender como criar uma margem sem comprometer o essencial.')
    p = state['draft']
    candidates = [('shopping', 'lojas e sites', dec(p['shoppingCurrent'])),
                  ('delivery', 'delivery e refeições fora', dec(p['deliveryCurrent']))]
    key, category, amount = max(candidates, key=lambda item: item[2])
    if amount > 0:
        event = 'compra pontual importante' if key == 'shopping' else 'despesa pontual importante'
        question = (f'Uma categoria que podemos avaliar é {category}, com {brl(str(amount))} no período. Nesse total, '
                    f'houve alguma {event} ou são gastos que costumam se repetir?')
        focus = {'category': key, 'label': category, 'observed': format(amount, '.2f'), 'period': period}
    else:
        question = ('Para não sugerir um ajuste no lugar errado, qual despesa essencial você precisa manter protegida '
                    'no seu planejamento?')
        focus = None
    return {'phase': 'understand_spending', 'message': profile_sentence(state) + observation + '\n\n' + question,
            'focus': focus}
