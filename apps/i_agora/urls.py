"""Montado em /api/v1/context-agent/i-agora/ por desafio_itau/urls.py (antes do include de context_agent_datadriven,
para este app responder por i-agora/plano/proposta/ e despachar o contrato antigo, ver views.proposal)."""
from django.urls import path

from . import views

app_name = 'i_agora'

urlpatterns = [
    path('perfil/', views.profile, name='perfil'),
    path('sessao/abertura/', views.opening, name='abertura'),
    path('plano/', views.plan, name='plano'),
    path('plano/proposta/', views.proposal, name='proposta'),
    path('plano/rascunho/', views.adjust, name='rascunho'),
    path('plano/confirmar/', views.confirm, name='confirmar'),
    path('acompanhamento/', views.followup, name='acompanhamento'),
]
