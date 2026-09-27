"""
Models do aplicativo context-agent-datadriven.
Arquitetura de Harness e Roteamento:
- Aponta para a base de 'rotas' (template .yaml com informações base de cada categoria)
- Delega para 'agentes/agente.py' a distribuição das chamadas conforme o protocolo de negociação
"""

from django.db import models
from .agentes.agente import AgenteNegotiatorEngine

class AgenteSecretConfig(models.Model):
    """Configuração e auditoria de credencial / Secret do gsconsole."""
    nome_secret = models.CharField(max_length=100, default="gsconsole-gemini-secret", unique=True)
    origem = models.CharField(max_length=100, default="Google Cloud Secret Manager / gsconsole")
    ativo = models.BooleanField(default=True)
    modelo_padrao = models.CharField(max_length=80, default="gemini-flash-latest")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nome_secret} ({'Ativo' if self.ativo else 'Inativo'})"

class ConversaAgenteSessao(models.Model):
    """
    Sessão de comunicação do Agente com Harness.
    Roteamento:
    1. Aponta para a base de 'rotas' (rotas_base.yaml) para mapear a categoria correspondente.
    2. Delega para 'agentes/agente.py' para a distribuição das chamadas com protocolo de negociação.
    """
    # Uma sessão por cliente: a view usa get_or_create(cliente_id=...), que só é
    # seguro com unicidade no banco (sem ela, duas criações concorrentes duplicam
    # a sessão e o get_or_create seguinte levanta MultipleObjectsReturned).
    cliente_id = models.IntegerField(default=42, unique=True)
    cliente_nome = models.CharField(max_length=150, default="Cliente Itaú")
    cliente_genero = models.CharField(max_length=1, default="F")
    score_comportamental = models.IntegerField(default=750)
    indice_corte = models.CharField(max_length=50, default="CTX-750-ALPHA")
    
    # Data de corte fixa: 22 de dezembro de 2025
    data_corte_fixa = models.CharField(max_length=20, default=AgenteNegotiatorEngine.DATA_CORTE_FIXA)
    horario_casado = models.CharField(max_length=20, default="14:35:20")
    
    iniciado_em = models.DateTimeField(auto_now_add=True)

    # despachar_chamada_harness (usado só por enviar-mensagem/) saiu na Decisão D-3, 2026-09-27:
    # archive/2026-09-27/apps/context_agent_datadriven/models.py.

    def __str__(self):
        return f"Sessão #{self.id} - Cliente #{self.cliente_id} (Corte {self.data_corte_fixa} {self.horario_casado})"

class MensagemAgenteRegistro(models.Model):
    """Histórico de mensagens no Harness com registro de horário casado."""
    sessao = models.ForeignKey(ConversaAgenteSessao, related_name='mensagens', on_delete=models.CASCADE)
    papel = models.CharField(max_length=20)
    conteudo = models.TextField()
    secret_utilizado = models.CharField(max_length=100, default="gsconsole:GEMINI_API_KEY")
    horario_registro = models.CharField(max_length=20, default="14:35:20")
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.papel} @ {self.horario_registro}] {self.conteudo[:40]}..."


class SessaoPerfilUsuario(models.Model):
    """
    Sessão de perfil-usuario ("quem sou eu"), persistida no SQLite para sobreviver ao reinício do
    processo (Decisão D-4, 2026-09-27). Antes era um dict em memória em services/perfil_usuario.py.
    `criada_em` é época Unix (segundos); o TTL (4 h) é aplicado na leitura, pelo serviço.
    """
    sessao_id = models.CharField(max_length=64, primary_key=True)
    usuario_json = models.TextField()
    criada_em = models.FloatField(db_index=True)

    def __str__(self):
        return f"SessaoPerfilUsuario {self.sessao_id[:8]}..."
