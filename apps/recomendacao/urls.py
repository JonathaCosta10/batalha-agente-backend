"""
Rotas e Arquitetura de URLs do Aplicativo de Recomendação.

Estrutura organizada por responsabilidade:
  - Navegação e visualização de templates (HTML)
  - Endpoints REST para o App Android (JSON)
  - Chave ON - OFF 'inteiração-tela-iai'
  - Endpoints dos Grupos Fixos Feminino e Masculino
  - Endpoints de Contexto Comportamental e Índice de Corte
  - Endpoints da Planilha Fixa (Template 3)
"""

from django.urls import path
from . import views

app_name = 'recomendacao'

urlpatterns = [
    # -------------------------------------------------------------------------
    # 1. Roteamento de Visualização de Templates (Server-Side)
    # -------------------------------------------------------------------------
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('chat/<int:cliente_id>/', views.TemplateChatView.as_view(), name='template_chat'),
    path('comunicacao/<int:cliente_id>/', views.TemplateMatrixView.as_view(), name='template_matrix'),

    # -------------------------------------------------------------------------
    # 2. Arquitetura de APIs RESTful para o App Android Demo
    # -------------------------------------------------------------------------
    # Chave ON - OFF 'inteiração-tela-iai'
    path('chave-interacao-tela-iai/', views.ChaveInteracaoTelaIAIAPI.as_view(), name='api_chave_interacao'),

    # Clientes no recorte dos 1.000 perfis
    path('cliente/random/', views.ClienteRandomicoAPI.as_view(), name='api_cliente_random'),
    path('cliente/<int:cliente_id>/', views.ClienteDetalheAPI.as_view(), name='api_cliente_detalhe'),

    # Auditoria e Estatísticas dos Grupos Fixos (F e M)
    path('grupos-fixos/', views.GruposFixosAPI.as_view(), name='api_grupos_fixos'),

    # Variável 1: Conversa pré-preenchida (baseada em ID -> F/M e chave ON/OFF)
    path('chat/variavel-1/<int:cliente_id>/', views.ChatVariavel1API.as_view(), name='api_chat_variavel_1'),

    # Disparo do botão 'E agora?' -> Interface de Comunicação
    path('comunicacao/e-agora/<int:cliente_id>/', views.ComunicacaoEAgoraAPI.as_view(), name='api_comunicacao_e_agora'),

    # Ponto de Índice e Corte de Contexto Comportamental
    path('contexto-score/<int:cliente_id>/', views.ContextoScoreAPI.as_view(), name='api_contexto_score'),

    # Variável Template 3: Planilha fixa de dados
    path('planilha-fixa/', views.PlanilhaFixaAPI.as_view(), name='api_planilha_fixa'),
]
