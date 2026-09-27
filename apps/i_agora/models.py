"""Estado do plano por sessão. No agent_backend era um SQLite à parte (/tmp/i-agora-plans.sqlite3, tabelas
plans/active/replay/picks); aqui vive no mesmo banco do Django. `picks` não existe: o cliente sorteado é o
titular da sessão (perfil_usuario, model SessaoPerfilUsuario)."""
from django.db import models


class PlanoIAgora(models.Model):
    """Um plano por (dono, cliente). `estado_json` é o state devolvido ao front, com o snapshot da fonte."""
    dono = models.CharField(max_length=128)
    ref = models.CharField(max_length=64)
    estado_json = models.TextField()
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['dono', 'ref'], name='plano_iagora_dono_ref')]


class PlanoAtivo(models.Model):
    """Qual plano (cliente) está ativo para o dono."""
    dono = models.CharField(max_length=128, primary_key=True)
    ref = models.CharField(max_length=64)


class ConfirmacaoPlano(models.Model):
    """Idempotência da confirmação: mesmo clientRequestId + mesmo conteúdo -> mesma resposta (replayed)."""
    dono = models.CharField(max_length=128)
    pedido_id = models.CharField(max_length=80)
    digest = models.CharField(max_length=64)
    resposta_json = models.TextField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['dono', 'pedido_id'], name='confirmacao_plano_dono_pedido')]
