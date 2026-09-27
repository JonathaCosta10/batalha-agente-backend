"""
Módulo de Cálculo e Corte de Contexto Comportamental.
Responsável por gerar o Ponto de Índice (Score de Contexto) e estruturar
a contextualização que alimentará o Agente de Prompt na Batalha de Agentes.
"""

from typing import Dict, Any, List

class BehavioralScoreEngine:
    """
    Engine de contextualização orientada a dados de comportamento.
    O índice de corte dita os guardrails e o tom do agente de prompt.
    """

    @staticmethod
    def calcular_indice_contexto(cliente: Dict[str, Any]) -> Dict[str, Any]:
        score = cliente["score_comportamental"]
        genero = cliente["genero"]
        nome = cliente["nome"]

        # Definição dos limiares de corte do índice
        if score >= 750:
            nivel = "ALTO"
            indice_code = "CTX-750-ALPHA"
            temperatura_agente = 0.3
            foco_estrategico = "Retenção de valor, diversificação patrimonial e produtos premium"
            tom_comunicacao = "Executivo, consultivo, seguro e proativo"
            gatilho_acao = "Apresentar condições exclusivas de alocação e cashback diferenciado"
        elif score >= 450:
            nivel = "MEDIO"
            indice_code = "CTX-450-BETA"
            temperatura_agente = 0.5
            foco_estrategico = "Crescimento sustentável, proteção familiar e consolidação de dívidas"
            tom_comunicacao = "Colaborativo, estruturado, orientador e encorajador"
            gatilho_acao = "Oferecer simulações comparativas e otimização de limites"
        else:
            nivel = "BAIXO"
            indice_code = "CTX-150-GAMMA"
            temperatura_agente = 0.2
            foco_estrategico = "Educação financeira, regularização, economia imediata e simplicidade"
            tom_comunicacao = "Acolhedor, didático, transparente e sem jargões"
            gatilho_acao = "Apresentar alternativas de alívio e reserva de emergência descomplicada"

        # Formatação do bloco de prompt de sistema (Contextualização do Agente)
        prompt_contextualizacao = (
            f"[SISTEMA: AGENTE ITAÚ BATALHA DE AGENTES TIME 2]\n"
            f"INDICE_CORTE: {indice_code} | NIVEL_PROPENSAO: {nivel} (Score: {score}/1000)\n"
            f"CLIENTE_ID: {cliente['id']} | NOME: {nome} | GENERO: {genero}\n"
            f"DIRETRIZ_COMPORTAMENTAL: {cliente['diretriz_comportamental']}\n"
            f"FOCO_ESTRATEGICO: {foco_estrategico}\n"
            f"TOM_VOZ: {tom_comunicacao}\n"
            f"GATILHO_OPERACIONAL: {gatilho_acao}\n"
            f"GUARDRAIL: Nunca prometer rentabilidade garantida e manter conformidade estrita com normas Bacen/CVM."
        )

        return {
            "score": score,
            "nivel": nivel,
            "indice_code": indice_code,
            "temperatura_agente": temperatura_agente,
            "foco_estrategico": foco_estrategico,
            "tom_comunicacao": tom_comunicacao,
            "gatilho_acao": gatilho_acao,
            "prompt_contextualizacao": prompt_contextualizacao,
        }
