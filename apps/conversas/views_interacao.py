"""POST conversas/interacao/ e GET conversas/avaliacoes/resumo/. Contrato: docs/contrato-api-frontend.md §5.3.

Sessão: SÓ pelo header `X-Sessao-Id` (o `sessao_id` de POST perfil-usuario/definir/). Sem cookie, portanto sem
CSRF: um header próprio não sai de formulário de outro site sem preflight CORS, e o CORS só aceita as origens do
front (settings.FRONT_ORIGENS: localhost/127.0.0.1 nas portas 3000 e 3001, Decisão D-5, 2026-09-27; CORS_ALLOW_ALL=1
reabre para qualquer origem). Um site de outra origem não recebe o preflight aprovado.

D-15 / D9 (2026-09-27): toda resposta de conversas/interacao/ (200, 4xx e 503) leva schema_version
interacao.SCHEMA_VERSION ("1.1"). O resumo de avaliações (outra rota) segue "1.0".
"""
import json
import os
import re

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from apps.context_agent_datadriven.services import perfil_usuario
from desafio_itau.politica import erros_api

from . import interacao, interacao_avaliacao
from .views import configuracao


def _json(corpo, status=200):
    saida = JsonResponse(corpo, status=status, json_dumps_params={'ensure_ascii': False})
    saida['Cache-Control'] = 'no-store'
    saida['X-Content-Type-Options'] = 'nosniff'
    return saida


def _erro(codigo, mensagem, status, schema_version='1.0', **extra):
    return _json({'schema_version': schema_version, 'erro': codigo, 'mensagem': mensagem, **extra}, status)


def _erro_interacao(codigo, mensagem, status, **extra):
    # Todo erro de interacao/ leva o envelope erro_api (erros_api-v1.json): mensagem ao cliente em pt-BR e acao_cliente.
    return _erro(codigo, mensagem, status, schema_version=interacao.SCHEMA_VERSION,
                 erro_api=erros_api.erro_api(status, 'api'), **extra)


@csrf_exempt
def interacao_view(request):
    if request.method != 'POST':
        return _erro_interacao('metodo', 'Use POST.', 405)
    sid = (request.META.get('HTTP_X_SESSAO_ID') or '').strip()
    if not sid or len(sid) > 64:
        return _erro_interacao('sessao', 'Envie o header X-Sessao-Id com o sessao_id de POST perfil-usuario/definir/.', 401)
    try:
        titular = perfil_usuario.usuario_da_sessao(sid)
    except perfil_usuario.SessaoNaoEncontrada as erro:
        return _erro_interacao('sessao', str(erro), 404)
    if request.content_type != 'application/json' or len(request.body) > 8192:
        return _erro_interacao('schema', 'Corpo JSON de até 8 KB: {"etapa": "...", "escolha": "..."}.', 400)
    try:
        corpo = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return _erro_interacao('schema', 'JSON inválido.', 400)
    if not isinstance(corpo, dict) or set(corpo) - {'etapa', 'escolha', 'mensagem'} or not isinstance(corpo.get('etapa'), str) \
            or not isinstance(corpo.get('escolha'), (str, type(None))) or not isinstance(corpo.get('mensagem'), (str, type(None))):
        return _erro_interacao('schema', 'Campos aceitos: etapa (texto), escolha (id de botão, opcional) e mensagem (texto livre '
                     'do cliente, opcional, em qualquer etapa).', 400, etapas_validas=sorted(interacao.ETAPAS))
    cfg = configuracao()
    # input_guard pelo modelo gasta 1 pedido da quota por mensagem livre; INTERACAO_GUARD_ENTRADA_MODELO=0 desliga
    # (fica o classificador de domínio determinístico + guards de saída).
    guard_modelo = os.environ.get('INTERACAO_GUARD_ENTRADA_MODELO', '1') != '0'
    try:
        resposta = interacao.interagir(titular, corpo['etapa'], corpo.get('escolha'), mensagem=corpo.get('mensagem'),
                                       modo=cfg['MODO'], budget=int(cfg['MAX_CHAMADAS']),
                                       guard_entrada_modelo=guard_modelo, sessao_id=sid)
    except interacao.EtapaInvalida as erro:
        return _erro_interacao('etapa', str(erro), 400, etapas_validas=sorted(interacao.ETAPAS))
    except interacao.SemResposta as erro:
        # Antes (medido 10:14 BRT): 503 com texto null, sem `erro`, sem `mensagem` e erro_api null. Agora a tela recebe
        # a causa e o que fazer; o corpo da avaliação continua igual (aditivo).
        return _json({**erro.corpo, 'erro': 'sem_texto_aprovado',
                      'mensagem': 'Não consegui preparar uma resposta segura para esta etapa agora.',
                      'erro_api': erro.corpo.get('erro_api') or erros_api.erro_api(503, 'api')}, 503)
    return _json(resposta)


@csrf_exempt
def resumo_avaliacoes_view(request):
    if request.method != 'GET':
        return _erro('metodo', 'Use GET.', 405)
    data = request.GET.get('data')
    if data and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', data):
        return _erro('schema', 'data deve ser AAAA-MM-DD.', 400)
    return _json(interacao_avaliacao.resumo(data=data))
