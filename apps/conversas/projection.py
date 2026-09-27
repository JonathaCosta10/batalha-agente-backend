"""Deterministic monthly-spending projection, never a savings/wealth forecast.

Extracted proposals are untrusted: every field must occur in user messages,
then a separate explicit confirmation is required by ConversationService.
"""
import re
from decimal import Decimal, InvalidOperation, ROUND_CEILING, localcontext
from desafio_itau import politica
from .rules import folded

MONTHS = ['janeiro','fevereiro','marco','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro']


def project(current, target):
    try:
        a, b = Decimal(current), Decimal(target)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('Invalid money') from None
    if not a.is_finite() or not b.is_finite() or min(a,b)<0 or max(a,b)>Decimal('999999999999.99'):
        raise ValueError('Invalid money')
    if a <= b: return {'status':'already','n_5':0,'n_8':0}
    if b == 0: return {'status':'zero_target','n_5':None,'n_8':None}
    result: dict[str, object] = {'status':'projected'}
    with localcontext() as ctx:
        ctx.prec=80
        tolerance=max(a,b,Decimal(1))*Decimal('1e-60')
        # Hipóteses da regra `projecao.hipoteses_reducao` (desafio_itau/politica/operacional-v1.json).
        for rate,key in [(politica.parametro('projecao.hipoteses_reducao','r_5'),'n_5'),
                         (politica.parametro('projecao.hipoteses_reducao','r_8'),'n_8')]:
            base=1-rate
            n=int(((b/a).ln()/base.ln()).to_integral_value(rounding=ROUND_CEILING))
            while n>0 and a*base**(n-1)<=b+tolerance: n-=1
            while a*base**n>b+tolerance: n+=1
            result[key]=n
    return result


def money(raw):
    text=raw.strip().replace('R$','').replace(' ','')
    if not re.fullmatch(r'\d{1,12}(?:[.,]\d{1,3})*',text): raise ValueError('Invalid amount')
    if ',' in text: text=text.replace('.','').replace(',','.')
    elif re.fullmatch(r'\d{1,3}(?:\.\d{3})+',text): text=text.replace('.','')
    try:
        value=Decimal(text)
    except InvalidOperation:
        raise ValueError('Invalid amount') from None
    if value > Decimal('999999999999.99'): raise ValueError('Amount exceeds supported range')
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -2: raise ValueError('Use cents')
    return format(value,'.2f')


def month(raw):
    text=folded(raw.strip())
    m=re.fullmatch(r'(20\d{2})-(0[1-9]|1[0-2])',text)
    if m: return text
    m=re.fullmatch(r'(0?[1-9]|1[0-2])/(20\d{2})',text)
    if m: return f'{m[2]}-{int(m[1]):02d}'
    for i,name in enumerate(MONTHS,1):
        m=re.fullmatch(name+r'(?: de)? (20\d{2})',text)
        if m: return f'{m[1]}-{i:02d}'
    raise ValueError('Month/year required')


def validate_proposal(proposal, user_messages):
    texts=[folded(x) for x in user_messages]
    joined='\n'.join(texts)
    for value in proposal.values():
        if not isinstance(value,str) or not any(folded(value) in text for text in texts):
            raise ValueError('Unreported proposal field')
    if re.search(r'por semana|semanal|por dia|diario|por ano|anual|dolar|euro|usd|eur|mes parcial|gasto parcial',joined):
        raise ValueError('Comparability needs clarification')
    return {**proposal,'current_spending':money(proposal['current_spending']),
            'target_spending':money(proposal['target_spending']),
            'reference_month':month(proposal['reference_month'])}


def brl(value):
    return 'R$ '+format(Decimal(value),',.2f').replace(',','_').replace('.',',').replace('_','.')


def confirmation(p):
    return (f"Objetivo informado: {p['objective'].rstrip('.!?')}. Vamos considerar o mesmo conjunto de gastos com {p['category']}, "
        f"em reais por mês: de {brl(p['current_spending'])} para {brl(p['target_spending'])}, "
        f"a partir da referência {p['reference_month']}. Confirma esses dados como valores mensais comparáveis "
        "de um mês encerrado, para simular a redução gradual? Isso não registra um compromisso.")


def is_confirmation(text):
    return folded(text).strip(' .!') in {'sim','confirmo','sim, confirmo','sim confirmo','sim, pode calcular','pode calcular','isso','correto','confirmado'}


def explain(p, result):
    target=brl(p['target_spending'])
    if result['status']=='already':
        return f"Você já está no nível de gasto desejado para {p['category']}: prazo de zero meses. Nenhum compromisso foi registrado. Qual próximo passo gostaria de avaliar?"
    if result['status']=='zero_target':
        return 'Uma redução percentual composta não chega exatamente a zero em prazo finito. Você prefere definir um gasto-alvo positivo ou planejar a eliminação desse gasto por outra abordagem?'
    low,high=result['n_8'],result['n_5']
    span=f'{low} meses' if low==high else f'{low} a {high} meses'
    same=' Ambos os cenários apontam o mesmo prazo inteiro.' if low==high else ''
    return (f"Com hipóteses de redução mensal de 5% e 8% no gasto com {p['category']}, "
        f"a projeção é chegar a {target} mensais em aproximadamente {span}, a partir de {p['reference_month']}.\n\n"
        f"Redução mensal de 5%: {high} meses.\nRedução mensal de 8%: {low} meses.{same}\n\n"
        "A cada mês, a redução incide sobre o gasto projetado do mês anterior. São duas hipóteses constantes, "
        "não uma probabilidade, promessa ou regra do Itaú. Não é um prazo para acumular dinheiro. "
        "O cenário mais rápido não é uma obrigação; podemos recalcular com novos dados comparáveis. "
        "Nenhum compromisso foi registrado. Qual pequena mudança parece possível para você no próximo mês?")
