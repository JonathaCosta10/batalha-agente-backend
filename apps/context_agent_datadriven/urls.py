"""
Rotas e endpoints do aplicativo context-agent-datadriven.
"""

from django.urls import path
from . import views, views_perfil_usuario as pu, views_usuario_real as ur

from .views_controle_conversa import ControleConversaAPI

app_name = 'context_agent_datadriven'

urlpatterns = [
    # Painel visual
    path('', views.PainelAgenteView.as_view(), name='painel'),
    
    # Endpoints REST para comunicação com o Agente via gsconsole
    path('status-harness/', views.StatusHarnessAPI.as_view(), name='api_status_harness'),
    path('enviar-mensagem/', views.EnviarMensagemHarnessAPI.as_view(), name='api_enviar_mensagem'),
    path('primeira-chamada/', views.PrimeiraChamadaAPI.as_view(), name='api_primeira_chamada'),

    # Perfil de usuário: a primeira chamada do front define "quem sou eu" (CSV da verdade)
    path('perfil-usuario/definir/', pu.PerfilUsuarioDefinirAPI.as_view(), name='api_perfil_usuario_definir'),
    path('perfil-usuario/pergunta/', pu.PerfilUsuarioPerguntaAPI.as_view(), name='api_perfil_usuario_pergunta'),

    # Controle da conversa: roteiro de falas do front (docs/controle-da-conversa.md)
    path('controle-conversa/', ControleConversaAPI.as_view(), name='api_controle_conversa'),

    # Compromissos de janeiro pela modelagem i.agora (subcategoria real da tabela)
    path('i-agora/plano/proposta/', ur.PlanoPropostaAPI.as_view(), name='api_plano_proposta'),

    # Usuário real: extrato no BigQuery via ADC (contrato: docs/contrato-api-frontend.md)
    path('usuario-real/status/', ur.UsuarioRealStatusAPI.as_view(), name='api_usuario_real_status'),
    path('usuario-real/', ur.UsuarioRealListaAPI.as_view(), name='api_usuario_real_lista'),
    path('usuario-real/<str:referencia>/', ur.UsuarioRealPerfilAPI.as_view(), name='api_usuario_real_perfil'),
    path('usuario-real/<str:referencia>/visao/<str:topico>/', ur.UsuarioRealVisaoAPI.as_view(), name='api_usuario_real_visao'),
    path('usuario-real/<str:referencia>/saldo-mes/', ur.UsuarioRealSaldoMesAPI.as_view(), name='api_usuario_real_saldo_mes'),
    path('usuario-real/<str:referencia>/pergunta/', ur.UsuarioRealPerguntaAPI.as_view(), name='api_usuario_real_pergunta'),
]
