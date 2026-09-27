"""
URL configuration for desafio-itau-batalha-de-agentes-time2.

Redirecionamento principal do projeto para o aplicativo de recomendação e APIs.
Inclui o novo app context-agent-datadriven com comunicação via secret do gsconsole.
"""

from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    # Redirecionamento da raiz do projeto para o painel do aplicativo
    path('', RedirectView.as_view(url='/app/', permanent=False), name='root_redirect'),

    # Rotas do aplicativo de recomendação e interfaces de templates
    path('app/', include('apps.recomendacao.urls', namespace='recomendacao')),

    # Conversa i-agora (porte de agente-app-mobile/agent_backend): sessao/ e mensagens/. Antes dos includes
    # mais largos para ninguém capturar o prefixo. Contrato: docs/contrato-api-frontend.md, seção 5.2.
    path('api/v1/context-agent/conversas/', include('apps.conversas.urls', namespace='conversas')),

    # Rotas de API versionada (Arquitetura REST para o App Android)
    path('api/v1/', include(('apps.recomendacao.urls', 'api_v1'), namespace='api_v1')),

    # Novo App: context-agent-datadriven (Painel e APIs de comunicação com Agente via gsconsole)
    path('context-agent/', include('apps.context_agent_datadriven.urls', namespace='context_agent_datadriven')),
    path('api/v1/context-agent/', include(('apps.context_agent_datadriven.urls', 'api_context_agent'), namespace='api_context_agent')),
]
