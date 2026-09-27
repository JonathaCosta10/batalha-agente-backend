"""GET /healthz para o Cloud Run (startup e liveness probe). Criado em 2026-09-27.

Responde 200 {"status": "ok"} sem tocar em banco, BigQuery nem Gemini. Roda como o PRIMEIRO middleware, antes do
CORS, do CommonMiddleware e da validação de ALLOWED_HOSTS: a sonda do Cloud Run chega com um Host interno que não
está na lista de produção e, sem isso, receberia 400. Só o caminho exato /healthz (com ou sem barra final) e só
GET/HEAD; qualquer outro pedido segue o fluxo normal. Para saber se as dependências respondem, use as rotas de
status (`conversas/status/`, `usuario-real/status/?validar=1`), que não servem de sonda porque podem ir à rede.
"""
from django.http import JsonResponse

# /api/health/ (2026-09-27 12:38, pedido do dono): alguém sonda esta rota a cada 5 min e recebia 404. Alias leve.
CAMINHOS = ('/healthz', '/healthz/', '/api/health', '/api/health/')


def healthz(request):
    resposta = JsonResponse({'status': 'ok'})
    resposta['Cache-Control'] = 'no-store'
    return resposta


class HealthzMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in CAMINHOS and request.method in ('GET', 'HEAD'):
            return healthz(request)
        return self.get_response(request)
