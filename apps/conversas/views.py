"""Rotas /api/v1/context-agent/conversas/ (sessao/ e mensagens/). Contrato: docs/contrato-api-frontend.md, 5.2.

Portado de agente-app-mobile/agent_backend/conversation/http.py (commit 1302ba5), com o MESMO envelope
MessageResponse 1.0. Mudança de identidade: o cookie assinado `i_agora_demo_session` (só loopback) deu lugar
ao `sessao_id` de POST perfil-usuario/definir/. O front passa o `sessao_id` UMA vez, no GET sessao/
(`?sessao_id=` ou header `X-Sessao-Id`); o backend devolve um cookie assinado `conversa_sessao` e o POST
mensagens/ segue igual ao de A (cookie + `X-CSRFToken`). Header `X-Sessao-Id` no POST também vale e tem
precedência sobre o cookie. sessao_id explícito desconhecido, ou POST sem sessão: 404 com o envelope e o pedido
de chamar definir/. GET sessao/ sem sessão nenhuma (front do i-agora, 2026-09-27): sorteia a pessoa e cria a sessão.

CSRF: o projeto não tem CsrfViewMiddleware global; estas views aplicam o middleware do Django localmente
(GET sessao/ entrega o cookie `csrftoken`; POST mensagens/ exige `X-CSRFToken`), com a falha no envelope 403.
"""
import asyncio
import json
from functools import lru_cache, wraps

from django.conf import settings
from django.core import signing
from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from desafio_itau.modelos_llm import MODELO_PRIMEIRA_CHAMADA
from apps.context_agent_datadriven.services import perfil_usuario

from .persistencia import ArmazemConversas
from .service import ConversationService

errors = ConversationService()
COOKIE = 'conversa_sessao'
PADRAO = {'MODO': 'demo_live', 'MODELO': MODELO_PRIMEIRA_CHAMADA, 'MODELO_GUARD': MODELO_PRIMEIRA_CHAMADA,
          'MAX_CHAMADAS': 300, 'ROTEADOR': True}  # ROTEADOR: router por etapa/erro (roteador.py, 2026-09-27)
MODOS = ('demo', 'demo_live')


def configuracao():
    return {**PADRAO, **getattr(settings, 'CONVERSAS', {})}


@lru_cache(maxsize=4)
def service_for(mode, model, guard_model, budget, roteador=False):
    # I4 / D-4 (2026-09-27): a conversa sobrevive ao reinício do processo (persistencia.ArmazemConversas, TTL 4 h).
    if mode == 'demo':
        return ConversationService(persistencia=ArmazemConversas())
    if mode != 'demo_live':
        raise ValueError('Modo de conversa desconhecido')
    from .gateway import GeminiGateway
    # Plano i-agora (apps/i_agora, 2026-09-27): a conversa lê o plano do dono e entrega o caso de compromisso.
    from apps.i_agora.views import conversation_context, offer_case
    from .roteador import Roteador
    gw = GeminiGateway(model=model, guard_model=guard_model, max_calls=budget, roteador=Roteador() if roteador else None)
    return ConversationService(gateway=gw,
                               persistencia=ArmazemConversas(), principal_context_builder=conversation_context,
                               on_commitment_proposed=offer_case)


def get_service():
    cfg = configuracao()
    return service_for(cfg['MODO'], cfg['MODELO'], cfg['MODELO_GUARD'], int(cfg['MAX_CHAMADAS']), bool(cfg['ROTEADOR']))


CAMPOS_METRICA = ('stage', 'model', 'model_version', 'latency_ms', 'outcome', 'total_tokens', 'nova_chamada',
                  'tratamento_erro', 'politica_operacional', 'error_type', 'motivo_invalida', 'http_status')


def estado_harness():
    """GET conversas/status/: o que o harness está a usar AGORA neste processo. Sem texto, prompt nem identificador.
    O modelo real é o `modelVersion` devolvido pelo provedor na última chamada; sem chamada, diz NAO_MEDIDO."""
    from desafio_itau import politica
    from desafio_itau.politica import erros_api, lexico
    from .gateway import TIMEOUT_POR_ETAPA
    cfg, service = configuracao(), get_service()
    gw = service.gateway
    metricas = list(getattr(gw, 'metrics', ()))
    versao = next((m['model_version'] for m in reversed(metricas) if m.get('model_version')), None)
    lim = erros_api.carregar().limites
    return {
        'schema_version': '1.0', 'modo': cfg['MODO'],
        'modelo_configurado': cfg['MODELO'] if gw else None, 'modelo_guard': cfg['MODELO_GUARD'] if gw else None,
        'model_version_observado': versao or 'NAO_MEDIDO (nenhuma chamada ao provedor neste processo)',
        'orcamento_processo': ({'max_chamadas': gw.max_calls, 'usadas': gw.calls,
                                'restantes': max(gw.max_calls - gw.calls, 0)} if gw else None),
        'cota_diaria_provedor': 'NAO_MEDIDO: a API do Gemini não expõe a cota restante; o 429 é o sinal (erro_api)',
        # Modelos fora por 429 de cota DIÁRIA (quotaId PerDay), com os segundos até a próxima sonda real (gateway.py).
        'cota_diaria_esgotada': gw.cota_diaria_esgotada() if gw and hasattr(gw, 'cota_diaria_esgotada') else {},
        # Router (roteador.py): ordem por etapa, último modelo que respondeu em cada etapa, resfriamentos e RPM do
        # processo. null = sem router (modo demo ou CONVERSAS['ROTEADOR']=False).
        'roteador': gw.roteador.estado() if gw is not None and getattr(gw, 'roteador', None) is not None else None,
        'orcamento_diario': 'NAO_IMPLEMENTADO: o teto é por processo (MAX_CHAMADAS), não por dia',
        'limites': {'pedidos_por_minuto_por_usuario': service.requests_per_minute, 'turnos_por_conversa': service.max_turns,
                    'conversas_por_usuario': 5, 'ttl_conversa_s': service.ttl, 'timeout_s': service.timeout,
                    'timeout_por_etapa_s': dict(TIMEOUT_POR_ETAPA),
                    'novas_chamadas_max': lim.novas_chamadas_max, 'espera_max_no_servidor_s': lim.espera_max_no_servidor_s},
        'ultimas_chamadas': [{k: m.get(k) for k in CAMPOS_METRICA} for m in metricas[-20:]],
        'versoes': {'politica': politica.referencia_documento(), 'lexico': lexico.versao(),
                    'erros_api': f'{erros_api.carregar().id}@{erros_api.carregar().versao}'},
    }


def status_view(request):
    if request.method != 'GET':
        return failure('not_found', 405)
    return response((estado_harness(), 200))


def response(result):
    body, status = result
    output = JsonResponse(body, status=status, json_dumps_params={'ensure_ascii': False})
    output['Cache-Control'] = 'no-store'
    output['X-Content-Type-Options'] = 'nosniff'
    return com_retry_after(output, body, status)


def com_retry_after(output, body, status):
    """erros_api 1.2.0: 429/503/504 com espera conhecida levam `Retry-After` (segundos) — o front já lê o header."""
    espera = ((body or {}).get('erro_api') or {}).get('tentar_novamente_em_s') if isinstance(body, dict) else None
    if status in (429, 503, 504) and isinstance(espera, int) and espera > 0:
        output['Retry-After'] = str(espera)
    return output


def failure(code='auth', status=401, tipo=None):
    return response(errors.release(code=code, http_status=status, tipo=tipo))


def sessao_de(request, aceita_query=False):
    """-> (sessao_id, titular) ou (None, None). Header > query (só GET) > cookie assinado."""
    sid = request.META.get('HTTP_X_SESSAO_ID') or (request.GET.get('sessao_id') if aceita_query else None)
    if not sid:
        try:
            sid = signing.loads(request.COOKIES.get(COOKIE, ''), salt=COOKIE, max_age=perfil_usuario.SESSAO_SEGUNDOS)
        except (signing.BadSignature, ValueError, TypeError):
            return None, None
    sid = str(sid).strip()
    if not sid or len(sid) > 64:
        return None, None
    try:
        return sid, perfil_usuario.usuario_da_sessao(sid)
    except perfil_usuario.SessaoNaoEncontrada:
        return None, None


def envelope_de_erros(view):
    """Todo erro da feature sai no envelope 1.0: sem traceback, sem página de debug, sem texto do provedor."""
    @wraps(view)
    def envolvida(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except RequestDataTooBig:
            return failure('schema', 400)
        except Exception:
            return failure('technical', 503)
    return envolvida


class _Csrf(CsrfViewMiddleware):
    def _reject(self, request, reason):
        return failure('auth', 403)


def csrf_falha(request):
    """None se o token confere; senão o envelope 403."""
    checagem = _Csrf(lambda r: None)
    checagem.process_request(request)
    return checagem.process_view(request, None, (), {})


@csrf_exempt
@envelope_de_erros
@ensure_csrf_cookie
def bootstrap(request):
    if request.method != 'GET':
        return failure('schema', 405)
    sid, titular = sessao_de(request, aceita_query=True)
    if not titular:
        # sessao_id explícito (header ou query) e desconhecido: 404 pedindo definir/, como antes.
        if request.META.get('HTTP_X_SESSAO_ID') or request.GET.get('sessao_id'):
            return failure('sessao', 404)
        # Sem sessão nenhuma (ou cookie vencido): o front do i-agora (Frontend/src/services/backend.ts) chama
        # este GET direto. Como no agent_backend, a pessoa é sorteada aqui e fica na sessão até o "próximo
        # perfil" (apps/i_agora/sessao.py). 2026-09-27; antes respondia 404.
        from apps.i_agora.sessao import nova_sessao
        sid = nova_sessao()['sessao_id']
        titular = perfil_usuario.usuario_da_sessao(sid)
    mode = configuracao()['MODO']
    body, status = errors.release(code='demo' if mode == 'demo' else 'clarify', http_status=200)
    body['mode'] = mode
    body['usuario'] = dict(titular)
    output = response((body, status))
    output.set_cookie(COOKIE, signing.dumps(sid, salt=COOKIE), max_age=perfil_usuario.SESSAO_SEGUNDOS,
                      httponly=True, samesite='Lax', secure=request.is_secure())
    return output


@csrf_exempt
@envelope_de_erros
def message(request):
    if request.method != 'POST':
        return failure('schema', 405)
    rejeitado = csrf_falha(request)
    if rejeitado is not None:
        return rejeitado
    sid, titular = sessao_de(request)
    if not titular:
        return failure('sessao', 404)
    if request.content_type != 'application/json' or len(request.body) > 16384:
        return failure('schema', 400)
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return failure('schema', 400)
    return response(asyncio.run(get_service().send('sessao:' + sid, payload, titular=titular)))


@csrf_exempt
def nao_encontrado(request, *args, **kwargs):
    return failure('not_found', 404)
