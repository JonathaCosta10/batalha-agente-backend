"""
Models do aplicativo context-agent-datadriven.
Arquitetura de Harness e Roteamento:
- Aponta para a base de 'rotas' (template .yaml com informações base de cada categoria)
- Delega para 'agentes/agente.py' a distribuição das chamadas conforme o protocolo de negociação
"""

from django.db import models
from .rotas.manager import BaseDeRotasManager
from .agentes.agente import AgenteNegotiatorEngine, ORIGEM_MODELO

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

    def despachar_chamada_harness(self, mensagem_usuario: str, contexto_interno: dict) -> dict:
        """
        ROTEAMENTO:
        Models aponta primeiramente para a base de rotas (rotas_base.yaml)
        e distribui via 'agentes.agente.AgenteNegotiatorEngine' como protocolo de negociação.
        """
        horario = AgenteNegotiatorEngine.calcular_horario_casado(self.cliente_id)
        self.horario_casado = horario
        self.save(update_fields=['horario_casado'])

        # Consulta prévia à base de rotas YAML
        rota_info = BaseDeRotasManager.identificar_categoria(mensagem_usuario, self.score_comportamental)

        historico = []
        for m in self.mensagens.all().order_by("criado_em")[:8]:
            historico.append({"papel": m.papel, "conteudo": m.conteudo})

        # Distribuição de chamada pelo Agente através do protocolo de negociação
        resultado = AgenteNegotiatorEngine.distribuir_chamada(
            mensagem_usuario=mensagem_usuario,
            cliente_id=self.cliente_id,
            contexto_interno=contexto_interno,
            historico_mensagens=historico,
        )

        # Só grava o par quando um modelo respondeu. Em contingência nada é
        # gravado: o histórico (acima) é reenviado ao modelo nos turnos
        # seguintes, e um texto fixo gravado como papel "model" passaria a
        # ser tratado como algo que o modelo disse; e a mensagem do usuário
        # sem resposta ficaria duplicada quando o cliente reenviasse.
        if resultado.get("origem_resposta") != ORIGEM_MODELO:
            resultado["rota_mapeada"] = rota_info
            return resultado

        MensagemAgenteRegistro.objects.create(
            sessao=self,
            papel="user",
            conteudo=mensagem_usuario,
            secret_utilizado="gsconsole:GEMINI_API_KEY",
            horario_registro=horario,
        )
        MensagemAgenteRegistro.objects.create(
            sessao=self,
            papel="model",
            conteudo=resultado.get("resposta", ""),
            secret_utilizado=f"gsconsole:{resultado.get('protocolo_negociacao', {}).get('modelo_utilizado')}",
            horario_registro=horario,
        )

        # Enriquecimento com informações de rota para auditoria
        resultado["rota_mapeada"] = rota_info
        return resultado

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
