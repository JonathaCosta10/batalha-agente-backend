"""
Proxy de compatibilidade para agente/router.py.
Delega diretamente para a nova arquitetura:
apps/context_agent_datadriven/agentes/agente.py (AgenteNegotiatorEngine)
"""
from ..agentes.agente import AgenteNegotiatorEngine

class AgenteHarnessRouter:
    @classmethod
    def calcular_horario_casado(cls, cliente_id: int) -> str:
        return AgenteNegotiatorEngine.calcular_horario_casado(cliente_id)

    @classmethod
    def rotear_chamada_agente(cls, mensagem_usuario: str, cliente_id: int, contexto_interno: dict, historico_mensagens: list = None):
        return AgenteNegotiatorEngine.distribuir_chamada(
            mensagem_usuario=mensagem_usuario,
            cliente_id=cliente_id,
            contexto_interno=contexto_interno,
            historico_mensagens=historico_mensagens,
        )
