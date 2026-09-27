"""Montado em /api/v1/context-agent/conversas/ por desafio_itau/urls.py."""
from django.urls import path, re_path

from .views import bootstrap, message, nao_encontrado, status_view
from .views_interacao import interacao_view, resumo_avaliacoes_view

app_name = 'conversas'

urlpatterns = [
    path('mensagens/', message, name='mensagens'),
    path('sessao/', bootstrap, name='sessao'),
    # Estado do harness: modelo configurado x observado, orçamento, limites, últimas chamadas sem texto (§5.5)
    path('status/', status_view, name='status'),
    # Resposta por interação do front, avaliada em tempo de execução (contrato §5.3)
    path('interacao/', interacao_view, name='interacao'),
    path('avaliacoes/resumo/', resumo_avaliacoes_view, name='avaliacoes_resumo'),
    re_path(r'^.*$', nao_encontrado),  # qualquer outro caminho da feature: 404 no envelope 1.0
]
