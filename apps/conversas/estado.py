"""Estado explícito de cada resposta de conversas/mensagens/ e o contrato público que a acompanha.

O estado é decidido por CONDIÇÕES VERIFICADAS no servidor (rota do pipeline, estado dos dados do titular,
evidências citadas), nunca pelo texto da mensagem nem pelo que a LLM declara sobre si. A mesma entrada verificada
dá sempre o mesmo estado; parafrasear o pedido não muda permissões (tests/test_estado_contrato.py).

Transição inválida (ex.: número do extrato citado com dados NAO_MEDIDO/OFF) levanta TransicaoInvalida, e o
serviço responde com a resposta segura predefinida: a saída rejeitada nunca é liberada.

Tabela de estados e ações permitidas: desafio_itau/politica/operacional-v1.json#estados.
"""
from desafio_itau import politica
from desafio_itau.politica import lexico
from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora import guard as guard_i_agora

from .schemas import ContratoRespostaV1

ORIGEM_EXTRATO = 'bigquery_extrato'
ROTAS = ('extremo', 'recusa', 'esclarecimento', 'identidade', 'simulacao', 'confirmacao_projecao', 'rascunho',
         'tecnico', 'demo')
POR_CODIGO = {'denied': 'RECUSA_SEGURA', 'clarify': 'ESCLARECIMENTO', 'demo': 'EDUCACAO_GERAL'}


class TransicaoInvalida(ValueError):
    pass


def _fatos(context):
    return {f['id']: f for f in (context or {}).get('facts', [])}


def claims_do_extrato(draft, context):
    fatos = _fatos(context)
    return [c for c in draft.claims if c.kind == 'financial'
            and fatos.get(c.evidence_id, {}).get('origin') == ORIGEM_EXTRATO]


def decidir(rota, *, dados_estado=None, draft=None, context=None):
    if rota not in ROTAS:
        raise TransicaoInvalida(f'rota desconhecida: {rota}')
    fixo = {'extremo': 'ENCAMINHAMENTO', 'recusa': 'RECUSA_SEGURA', 'esclarecimento': 'ESCLARECIMENTO',
            'identidade': 'IDENTIFICACAO', 'simulacao': 'SIMULACAO', 'confirmacao_projecao': 'ESCLARECIMENTO',
            'tecnico': 'INDISPONIVEL', 'demo': 'EDUCACAO_GERAL'}
    if rota in fixo:
        return fixo[rota]
    if claims_do_extrato(draft, context):
        if dados_estado != 'MEDIDO':
            raise TransicaoInvalida('fato do extrato citado sem dados medidos')
        return 'ANALISE_DESCRITIVA'
    if draft.status == 'needs_clarification':
        return 'ESCLARECIMENTO'
    if draft.status == 'safe_redirect':
        return 'RECUSA_SEGURA'
    if dados_estado != 'MEDIDO' and 'dados_financeiros_do_titular' in (draft.missing_data or []):
        return 'DADOS_INSUFICIENTES'
    return 'EDUCACAO_GERAL'


def fontes_numericas(context):
    """Valores que um número do texto pode citar: fatos do contexto + referências publicadas da política."""
    valores = []
    for fato in (context or {}).get('facts', []):
        try:
            valores.append(float(str(fato.get('value'))))
        except (TypeError, ValueError):
            continue
    for regra in politica.carregar().regras:
        for p in regra.parametros.values():
            valores.append(float(p.decimal) * (100 if p.unidade == 'fracao' else 1))
    return valores


def numeros_sem_fonte(texto, context):
    """R$ e % do texto que não batem (na precisão escrita) com nenhuma fonte. Lista vazia = todos sustentados."""
    fontes = fontes_numericas(context)
    return [n['bruto'] for n in guard_i_agora.numeros_do_texto(texto)
            if not any(abs(f - n['valor']) <= n['tolerancia'] + 1e-9 for f in fontes)]


RACIONAL = {
    'ENCAMINHAMENTO': ('mensagem com sinal de extremo detectado por regra', 'extremos.detectar',
                       'encaminhar para atendimento, sem modelo'),
    'RECUSA_SEGURA': ('pedido de terceiro ou finalidade prejudicial', 'input_guard/politica',
                      'oferecer alternativa segura'),
    'ESCLARECIMENTO': ('intenção ou dado ainda não confirmado', 'estado.esclarecimento', 'fazer uma pergunta'),
    'IDENTIFICACAO': ('pergunta sobre a própria identidade da sessão', 'perfil_usuario.conferir',
                      'informar nome e código do cadastro de demonstração'),
    'DADOS_INSUFICIENTES': ('dados do titular não medidos nesta resposta', 'context.dados_do_titular',
                            'orientação geral, sem números do titular'),
    'EDUCACAO_GERAL': ('nenhum fato do titular citado', 'estado.educacao_geral', 'orientação geral'),
    'ANALISE_DESCRITIVA': ('fatos do extrato medidos e citados com evidence_id', 'rules.valid_evidence',
                           'descrever os fatos, sem recomendação de produto'),
    'SIMULACAO': ('valores informados e confirmados pelo cliente', 'projecao.hipoteses_reducao',
                  'apresentar simulação com premissas, sem promessa'),
    'INDISPONIVEL': ('falha técnica ou validação reprovada', 'service.release',
                     'resposta segura predefinida; a saída rejeitada não é liberada'),
}


def contrato(estado, *, draft=None, context=None, extra_regras=()):
    tabela = politica.estados()
    observado, regra, consequencia = RACIONAL[estado]
    context = context or {}
    dados = context.get('dados_usuario') or {}
    regras = [f'estado.{estado.lower()}@{politica.carregar().estados.versao}', f'lexico@{lexico.versao()}',
              *extra_regras]
    corpo = {
        'schema_version': '1.0', 'estado': estado,
        'periodo': dados.get('janela') if dados.get('estado') == 'MEDIDO' else None,
        'evidence_ids': list(dict.fromkeys(c.evidence_id for c in draft.claims)) if draft else [],
        'regras_aplicadas': regras,
        'acoes_permitidas': list(tabela[estado].acoes_permitidas),
        'informacoes_faltantes': list((draft.missing_data if draft and draft.missing_data
                                       else context.get('missing_data', [])))[:12],
        'limitacoes_materiais': list(context.get('limitations', []))[:6],
        'racional': [{'observado': observado, 'regra': regra, 'consequencia': consequencia}],
    }
    return ContratoRespostaV1.model_validate(corpo).model_dump()
