"""A commitment is a grounded conversational case, not a projection or greeting.

Copiado sem mudança de Frontend/agent_backend/conversation/commitments.py (2026-09-27), com o plano i-agora.
"""
from .rules import folded
from .projection import money,brl
import re


def literal_clause(value,source,field):
    # Select an unchanged clause of the referenced statement, never invent a summary.
    clauses=[c.strip() for c in re.split(r'(?<=[.!?])\s+|;\s*',source) if c.strip()]
    if field=='action':
        clauses=[c for c in clauses if not re.search(r'R\$|\d+[,.]\d{2}\b',c)]
    words=set(re.findall(r'\w+',folded(value)))-{'a','o','e','de','do','da','os','as','com','em','na','no','para','que','um','uma'}
    score=lambda c:len(words & set(re.findall(r'\w+',folded(c))))
    if not clauses:raise ValueError('A ação precisa ser esclarecida sem reutilizar um valor anterior.')
    clause=max(clauses,key=score)
    if score(clause)<2:raise ValueError('Trecho não sustentado pela fala indicada.')
    return clause


def validate_case(proposal,user_messages,reference_month):
    proposal=dict(proposal)
    # Source IDs reference actual user statements, never model-authored summaries.
    refs=proposal.pop('source_refs',None)
    if refs:
        for field in ('objective','personal_context','action','monthly_amount'):
            index=refs[field]
            if type(index)!=int or not 1<=index<=len(user_messages):raise ValueError('Referência de conversa inválida.')
            source=user_messages[index-1]
            if folded(proposal[field]) not in folded(source):
                if field=='monthly_amount' or len(source)>500:raise ValueError('Trecho não encontrado na fala indicada.')
                proposal[field]=literal_clause(proposal[field],source,field)
    texts=[folded(x) for x in user_messages if x.strip()]
    if len(texts)<2:raise ValueError('Converse sobre seu contexto antes de montar a proposta.')
    for field in ('objective','personal_context','action','monthly_amount'):
        value=proposal[field]
        if not value.strip() or not any(folded(value) in text for text in texts):
            raise ValueError('A proposta contém uma informação que a pessoa não forneceu.')
    if not refs and len({folded(proposal[k]).strip() for k in ('objective','personal_context','action')})<3:
        raise ValueError('Objetivo, contexto e ação precisam estar esclarecidos.')
    if proposal['reference_month']!=reference_month:raise ValueError('Referência diferente da base observada.')
    if proposal['category'] not in ('delivery','shopping','other','reserve'):raise ValueError('Categoria não suportada.')
    return {**proposal,'monthly_amount':money(proposal['monthly_amount'])}


def explain(case,baseline):
    category=case['category'];amount=brl(case['monthly_amount'])
    if category in ('delivery','shopping'):
        label='delivery e refeições fora' if category=='delivery' else 'lojas e sites'
        target=f"Meta mensal em {label}: de {brl(str(baseline[category+'Current']))} observados para {amount}."
    elif category=='reserve':target=f'Meta: separar {amount} por mês para a reserva, respeitando a disponibilidade observada.'
    else:target=f'Meta: reduzir {amount} por mês em outros gastos escolhidos por você, preservando o essencial.'
    return (f"Pelo que conversamos, seu objetivo é: {case['objective'].rstrip('.!?')}.\n\n"
            f"O que precisamos respeitar: {case['personal_context'].rstrip('.!?')}.\n"
            f"Mudança que você considera viável: {case['action'].rstrip('.!?')}.\n\n"
            f"{target} A referência é {case['reference_month']}, da base sintética consultada. "
            "Isso é uma proposta para revisar, não um resultado garantido nem uma meta já salva. "
            "Se representa o que você quer, aprove no painel. Se não, me diga o que ajustar.")
