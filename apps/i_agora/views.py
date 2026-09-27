"""Rotas /api/v1/context-agent/i-agora/ (contrato do front: Frontend/src/services/backend.ts).

Portado de Frontend/agent_backend/planning/http.py (2026-09-27). Mudanças:
- identidade: a sessão é a de apps/conversas (cookie assinado `conversa_sessao` entregue pelo GET
  conversas/sessao/, ou header X-Sessao-Id); o dono do plano é 'sessao:<sessao_id>', o mesmo principal da conversa,
  e o cliente do plano é o titular da sessão (apps/i_agora/sessao.py);
- CSRF: o projeto não tem CsrfViewMiddleware global; POST/PATCH/DELETE daqui passam pela mesma checagem local
  de apps/conversas (X-CSRFToken + Origin confiável), com falha no envelope 403;
- i-agora/plano/proposta/ serve dois contratos (ver `proposal`).
"""
import json
import re
from functools import lru_cache, wraps

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from apps.conversas import views as conversas
from desafio_itau.politica import erros_api

from .domain import from_snapshot
from .fonte import FonteExtrato, SourceUnavailable
from .opening import guided_opening
from .sessao import trocar_cliente
from .store import Conflict, PlanStore

INSEGUROS = ('POST', 'PUT', 'PATCH', 'DELETE')


@lru_cache(maxsize=1)
def store():
    return PlanStore()


@lru_cache(maxsize=1)
def source():
    return FonteExtrato()


def public(s):
    if s is None:
        return None
    # state.opening: o front mostra no clique do i-agora; sem ele cai em "Ainda não recebi os dados…".
    return {**{k: v for k, v in s.items() if k != 'snapshot'}, 'opening': guided_opening(s)}


# `codigo` legado do corpo -> tipo de erro_api (erros_api-v1.json 1.2.0). O `codigo` string fica (compatível).
TIPO_POR_CODIGO = {'auth': 'sessao_ausente', 'source': 'fonte_indisponivel', 'stale': 'plano_desatualizado',
                   'schema': 'schema', 'technical': 'interno'}


def response(data, status=200, tipo=None):
    if status >= 400 and 'erro_api' not in data:
        # Todo erro de i-agora/* leva erro_api {codigo numérico, tipo estável, acao_cliente...}, nunca null.
        tipo = tipo or TIPO_POR_CODIGO.get(data.get('codigo')) or erros_api.tipo_de(status, 'api')
        data = {**data, 'erro_api': erros_api.erro_api(status, 'api', tipo=tipo)}
    r = JsonResponse(data, status=status)
    r['Cache-Control'] = 'no-store'
    r['X-Content-Type-Options'] = 'nosniff'
    return conversas.com_retry_after(r, data, status)


def body(request):
    if request.content_type != 'application/json' or len(request.body) > 16000:
        raise ValueError('Use JSON de até 16 KB.')
    data = json.loads(request.body)
    if not isinstance(data, dict):
        raise ValueError('Corpo inválido.')
    return data


def forget_conversation(principal):
    conversas.get_service().forget(principal)


def endpoint(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.method in INSEGUROS:
            rejeitado = conversas.csrf_falha(request)
            if rejeitado is not None:
                return rejeitado
        sid, titular = conversas.sessao_de(request)
        if not titular:
            return response({'erro': 'Sessão não autorizada. Reabra a conversa.', 'codigo': 'auth'}, 401)
        principal = 'sessao:' + sid
        try:
            return view(request, principal, sid, titular, *args, **kwargs)
        except SourceUnavailable as e:
            return response({'erro': str(e), 'estado': 'NAO_MEDIDO', 'codigo': 'source'}, 503)
        except Conflict as e:
            return response({'erro': str(e), 'codigo': 'stale', 'state': public(store().get(principal))}, 409,
                            tipo=getattr(e, 'tipo', 'plano_desatualizado'))
        except (ValueError, TypeError, KeyError) as e:
            return response({'erro': str(e)[:200] or 'Dados inválidos.', 'codigo': 'schema'}, 400)
        except Exception:
            return response({'erro': 'Não foi possível concluir a operação. Nada foi confirmado.', 'codigo': 'technical'},
                            503)
    return csrf_exempt(wrapped)


def profile_source(view):
    """Perfil/abertura nunca respondem com pessoa vazia ou genérica: falha da fonte é um 503 claro."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except SourceUnavailable as e:
            return response({'erro': 'perfil_indisponivel', 'motivo': str(e), 'estado': 'NAO_MEDIDO', 'codigo': 'source'},
                            503)
    return wrapped


def _abrir(principal, ref):
    """Plano ativo do cliente `ref` (lê a fonte só se ainda não há plano desse cliente para o dono)."""
    current = store().get(principal)
    if current and current['snapshot']['client_ref'] == ref:
        return current
    return store().open(principal, from_snapshot(source().load_ref(ref)))


@endpoint
@profile_source
def profile(request, principal, sid, titular):
    if request.method != 'GET':
        return response({'erro': 'Método não permitido.'}, 405)
    state = _abrir(principal, titular['codigo'])
    return response({**state['profile'], 'state': public(state)})


@endpoint
@profile_source
def opening(request, principal, sid, titular):
    if request.method != 'POST':
        return response({'erro': 'Método não permitido.'}, 405)
    data = body(request)
    if set(data) - {'origem', 'next'}:
        raise ValueError('Campos não permitidos.')
    ref = titular['codigo']
    if data.get('next') is True:
        forget_conversation(principal)
        ref = trocar_cliente(sid, atual=ref)
    state = _abrir(principal, ref)
    return response({'person': state['profile']['person'], 'state': public(state)}, 201)


@endpoint
def plan(request, principal, sid, titular):
    if request.method == 'GET':
        return response({'state': public(store().get(principal))})
    if request.method == 'DELETE':
        forget_conversation(principal)
        return response({'state': public(store().reset(principal))})
    if request.method == 'PATCH':
        data = body(request)
        version = data.pop('version')
        return response({'state': public(store().progress(principal, version, data))})
    return response({'erro': 'Método não permitido.'}, 405)


@endpoint
def _proposal(request, principal, sid, titular):
    if request.method == 'DELETE':
        return response({'state': public(store().withdraw_case(principal))})
    if request.method != 'POST':
        return response({'erro': 'Método não permitido.'}, 405)
    body(request)
    s = store().get(principal)
    if not s:
        raise SourceUnavailable('Carregue a base do cliente antes de propor metas.')
    if not s.get('commitmentCase'):
        raise Conflict('Vamos conversar primeiro sobre seu objetivo, contexto e uma mudança viável. '
                       'Ainda não há proposta para aprovar.', tipo='sem_proposta')
    return response({'state': public(s), 'basis': {'rule': 'conversation_grounded_case', 'seal': s['snapshot']['seal']}})


def _legado(request):
    """Contrato anterior desta rota (PlanoPropostaAPI: GET ?ref= ou POST {"ref", "data_corte"?}, sem sessão)."""
    if request.method == 'GET':
        return True
    if request.method != 'POST':
        return False
    try:
        data = json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        return True
    return not (isinstance(data, dict) and 'clientRequestId' in data)


@csrf_exempt
def proposal(request):
    """i-agora/plano/proposta/ tem dois contratos na mesma URL:
    - front do i-agora (backend.ts): POST {clientRequestId} lê o caso preparado pela conversa (409 sem caso) e
      DELETE retira o caso; ambos com sessão e CSRF, resposta {state};
    - contrato anterior deste backend (docs/contrato-api-frontend.md §4.7): GET ?ref= ou POST {"ref"} ->
      compromissos pela modelagem (views_usuario_real.PlanoPropostaAPI), sem sessão.
    O que decide é a presença de `clientRequestId` no corpo; DELETE é sempre do contrato novo."""
    if _legado(request):
        from apps.context_agent_datadriven.views_usuario_real import PlanoPropostaAPI
        return PlanoPropostaAPI.as_view()(request)
    return _proposal(request)


@endpoint
def adjust(request, principal, sid, titular):
    if request.method != 'PATCH':
        return response({'erro': 'Método não permitido.'}, 405)
    raise Conflict('Ajuste a proposta pela conversa para manter objetivo, ação e valor coerentes.')


@endpoint
def confirm(request, principal, sid, titular):
    if request.method != 'POST':
        return response({'erro': 'Método não permitido.'}, 405)
    data = body(request)
    if set(data) != {'clientRequestId', 'version', 'plan'} or not isinstance(data['clientRequestId'], str) \
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', data['clientRequestId']):
        raise ValueError('Confirmação inválida.')
    state = store().get(principal)
    if not state or not state.get('commitmentCase'):
        raise Conflict('Ainda não há uma proposta construída na conversa para aprovar.', tipo='sem_proposta')
    if data['plan'] != state['draft']:
        raise ValueError('A aprovação precisa corresponder à proposta apresentada. Peça o ajuste pela conversa.')
    result = store().confirm(principal, data['clientRequestId'], data['version'], data['plan'])
    return response({**result, 'state': public(result['state'])}, 200 if result['replayed'] else 201)


@endpoint
def followup(request, principal, sid, titular):
    if request.method != 'GET':
        return response({'erro': 'Método não permitido.'}, 405)
    state = store().get(principal)
    if not state or not state['confirmed']:
        return response({'erro': 'Nenhum objetivo confirmado.'}, 404, tipo='sem_objetivo_confirmado')
    p = state['confirmed']
    return response({'state': public(state),
                     'items': [{'category': c, 'spent': None, 'status': 'NAO_MEDIDO'} for c in p['selected']],
                     'message': 'Objetivos registrados. Evolução depende de novos movimentos comparáveis; '
                                'nenhum progresso foi inventado.'})


# ------------------------------------------------------------------ ganchos da conversa (apps/conversas/service.py)

def conversation_context(principal, context):
    """Acrescenta ao contexto da conversa o plano do dono: fatos do snapshot (BQ:*), período, base declarada e
    goal_state. Como no agent_backend, uma nova mensagem retira o caso ainda não aprovado (a conversa segue)."""
    s = store().withdraw_case(principal)
    if not s:
        return context
    snap = s['snapshot']
    p = s['profile']
    context['financial_period'] = snap['reference_month']
    context['plan_profile'] = {'situation': p['situation'], 'source': snap['seal'],
                               'inflows_are_not_recurring_income': True, 'arrears': None, 'debt': None}
    values = {'inflows': snap['inflows'], 'outflows': snap['outflows'], 'cash_flow': str(p['referencePeriod']['balance']),
              **{'category:' + k: v for k, v in snap['categories'].items()}}
    context.setdefault('facts', []).extend({'id': 'BQ:' + k, 'value': str(v), 'origin': snap['seal']['source'],
                                            'period': snap['reference_month']} for k, v in values.items())
    basis = '; '.join([snap['reference_month']] + [f'{k}: R$ {v.replace(".", ",")} por mês'
                                                   for k, v in snap['categories'].items()])
    group = s['draft']['deliveryCurrent']
    context['facts'].append({'id': 'BQ:group_delivery_restaurants', 'value': str(group),
                             'origin': 'deterministic_sum_of_Delivery_and_Restaurantes', 'period': snap['reference_month']})
    context['financial_input_basis'] = basis + f'; Delivery e refeições fora: R$ {group:.2f} por mês'.replace('.', ',')
    context['goal_state'] = {'planId': s['planId'], 'version': s['version'], 'commitment_case': s.get('commitmentCase'),
                             'draft': s['draft'], 'confirmed': s['confirmed'], 'confirmed_at': s['confirmedAt'],
                             'source': 'persistent_server_plan'}
    return context


def offer_case(principal, case, plan_id, version):
    return store().prepare_case(principal, version, plan_id, case)
