"""Small reviewed counter-speech route, not a keyword-based refusal classifier."""
import re
from .rules import folded
from .schemas import AgentDraftV1, Claim


def equality_draft(message, context):
    text=folded(message)
    # Respond to the wage discrimination proposition; never infer private salary facts.
    if not ('mulher' in text and re.search(r'homem|homens',text)
            and re.search(r'receber|ganhar|salari|remuner',text) and re.search(r'menos|inferior',text)):
        return None
    source=next((s for s in context['sources'] if s['id']=='ITAU-ETICA-2024:trabalho' and s['status']!='pending'),None)
    reply=('Não. Ser mulher não justifica receber menos do que um homem. A remuneração deve considerar critérios '
           'pertinentes ao trabalho, não o gênero da pessoa. ')
    claims=[]
    if source:
        claim='O Código de Ética e Conduta do Itaú, revisão de setembro de 2024, declara promover equidade e combater discriminação nas relações de trabalho.'
        reply+=claim+' Isso descreve o compromisso publicado, não comprova como cada caso é tratado. '
        claims=[Claim(kind='institutional',evidence_id=source['id'],text=claim)]
    reply+='Posso ajudar a pensar em critérios justos de remuneração.'
    return AgentDraftV1(reply=reply,status='safe_redirect',capabilities=['institucional'],claims=claims,missing_data=[])
