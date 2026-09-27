"""
Módulo Principal do Agente:
Distribui as chamadas conforme as rotas mapeadas no template .yaml como protocolo de negociação.
Localização: apps/context_agent_datadriven/agentes/agente.py
"""

from typing import Dict, Any, List, Optional
from ..rotas.manager import BaseDeRotasManager
from .LLM_Models import PROVEDORES_REGISTRADOS
from ..pastas_raiz.docs.tese_agente_docs import TESE_COMPLETA_CONTEXTUALIZADA
from ..pastas_raiz.controles_evals.evals_google_agent import executar_eval_harness
from desafio_itau.modelos_llm import MODELO_CONTINGENCIA
from desafio_itau.segredos import obter_api_key

# De onde veio o texto em "resposta": de um modelo que respondeu, ou do texto
# fixo de contingência quando nenhum respondeu.
ORIGEM_MODELO = "modelo"
ORIGEM_CONTINGENCIA = "contingencia"

class AgenteNegotiatorEngine:
    """
    Motor do Agente responsável pela negociação e distribuição mecânica de chamadas:
    - Roteamento via BaseDeRotasManager (template .yaml)
    - Protocolo de Negociação de Provedores (google -> antropic -> openIa)
    - Fixação temporal: Data de Corte 2025-12-22 e Horário Casado (24h)
    - Validação de Evals de Mercado da pasta_raiz
    """

    DATA_CORTE_FIXA = "2025-12-22"

    @classmethod
    def calcular_horario_casado(cls, cliente_id: int) -> str:
        """Calcula o horário casado dentro do dia 22/12/2025."""
        hora = (cliente_id * 7 + 9) % 24
        minuto = (cliente_id * 13 + 15) % 60
        segundo = (cliente_id * 19 + 25) % 60
        return f"{hora:02d}:{minuto:02d}:{segundo:02d}"

    @classmethod
    def distribuir_chamada(
        cls,
        mensagem_usuario: str,
        cliente_id: int,
        contexto_interno: Dict[str, Any],
        historico_mensagens: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Executa a distribuição de chamadas conforme o protocolo de negociação das rotas mapeadas.
        """
        horario_casado = cls.calcular_horario_casado(cliente_id)
        score = contexto_interno.get("score", 750)

        # 1. Roteamento pela Base de Rotas (YAML)
        rota_match = BaseDeRotasManager.identificar_categoria(mensagem_usuario, score)
        chave_cat = rota_match["chave_categoria"]
        detalhes_cat = rota_match["detalhes"]
        negociacao_cfg = detalhes_cat.get("protocolo_negociacao", {})

        provedor_primario = negociacao_cfg.get("provedor_primario", "google")
        modelo_primario = negociacao_cfg.get("modelo_primario", "gemini-flash-latest")
        provedores_alt = negociacao_cfg.get("provedores_alternativos", ["antropic", "openIa"])
        temperatura = negociacao_cfg.get("temperatura", 0.35)
        max_tokens = negociacao_cfg.get("max_tokens", 650)
        diretriz_foco = detalhes_cat.get("diretriz_template", {}).get("foco", "")

        # 2. Construção do Prompt de Sistema conforme Protocolo
        system_instruction = (
            f"[PROTOCOLO DE NEGOCIAÇÃO DO AGENTE ITAÚ - ROTA: {chave_cat.upper()}]\n"
            f"1. Temporalidade Casada: Seu relógio interno está sincronizado em {cls.DATA_CORTE_FIXA} às {horario_casado} BRT.\n"
            f"2. Contexto do Cliente: Atendendo {contexto_interno.get('nome')} (#{cliente_id}) - {contexto_interno.get('segmento')}.\n"
            f"3. Diretriz de Categoria: {diretriz_foco}\n"
            f"4. Sigilo de Dados Brutos (Fase 3): O score comportamental ({score}) e índices internos existem exclusivamente como contexto cognitivo. Jamais exiba notas, tabelas de cálculo ou índices brutos ao cliente.\n"
            f"5. Evidências: Embasado nas fontes auditadas da pasta_raiz ({len(TESE_COMPLETA_CONTEXTUALIZADA['fontes_de_evidencia'])} fontes de dados).\n"
            f"6. Tom: Consultivo, altamente seguro, acolhedor e focado no bem-estar financeiro."
        )

        # 3. Formatação dos contents
        contents = []
        if historico_mensagens:
            for item in historico_mensagens:
                papel = "user" if item.get("papel") in ["user", "usuario"] else "model"
                contents.append({"role": papel, "parts": [{"text": item.get("conteudo", "")}]})

        contents.append({"role": "user", "parts": [{"text": mensagem_usuario}]})

        # 4. Distribuição ao Provedor Primário (Google via gsconsole secret)
        cliente_provedor = PROVEDORES_REGISTRADOS.get(provedor_primario)
        resultado_chamada = None
        provedor_executado = provedor_primario
        modelo_executado = modelo_primario

        if cliente_provedor:
            resultado_chamada = cliente_provedor.executar_chamada(
                modelo=modelo_primario,
                system_instruction=system_instruction,
                contents=contents,
                temperatura=temperatura,
                max_tokens=max_tokens,
            )

        # 5. Fallback negociado se primário falhar
        if not resultado_chamada or not resultado_chamada.get("sucesso"):
            # Tenta o modelo de contingência da Google (desafio_itau.modelos_llm)
            if cliente_provedor and modelo_primario != MODELO_CONTINGENCIA:
                resultado_chamada = cliente_provedor.executar_chamada(
                    modelo=MODELO_CONTINGENCIA,
                    system_instruction=system_instruction,
                    contents=contents,
                    temperatura=temperatura,
                    max_tokens=max_tokens,
                )
                if resultado_chamada.get("sucesso"):
                    modelo_executado = MODELO_CONTINGENCIA

        # 6. Contingência: nenhum modelo respondeu (sem chave, rede, cota...).
        #    O texto abaixo NÃO veio de um modelo e o retorno diz isso:
        #    sucesso=False, origem_resposta="contingencia", provedor/modelo = None.
        origem_resposta = ORIGEM_MODELO
        erro_contingencia = None
        if not resultado_chamada or not resultado_chamada.get("sucesso"):
            origem_resposta = ORIGEM_CONTINGENCIA
            provedor_executado = None
            modelo_executado = None
            if not cliente_provedor:
                erro_contingencia = f"Provedor '{provedor_primario}' não registrado."
            else:
                erro_contingencia = (resultado_chamada or {}).get("erro") or "Nenhum modelo respondeu."
            if score >= 700:
                texto_fallback = (
                    f"Olá, {contexto_interno.get('nome', 'Cliente')}! Com base nas suas movimentações consolidadas até {cls.DATA_CORTE_FIXA}, "
                    f"identifiquei excelentes oportunidades para otimizar suas reservas em títulos privados pós-fixados com proteção e benefícios exclusivos."
                )
            else:
                texto_fallback = (
                    f"Olá, {contexto_interno.get('nome', 'Cliente')}! Analisando seu momento financeiro em {cls.DATA_CORTE_FIXA}, "
                    f"o passo mais seguro é priorizarmos a formação da sua reserva de emergência com liquidez diária e proteção FGC."
                )
            resultado_chamada = {
                "sucesso": False,
                "resposta": texto_fallback,
                "provider": None,
                "modelo": None,
            }

        texto_final = resultado_chamada.get("resposta", "")

        # 7. Execução dos Evals (também sobre o texto de contingência: o eval
        #    avalia o que seria mostrado, venha de onde vier) de Mercado (pasta_raiz)
        eval_resultado = executar_eval_harness(texto_final, horario_casado)

        # Uma resposta que falhou no filtro não pode sair no HTTP nem entrar
        # no histórico como se fosse uma resposta válida do modelo.
        if origem_resposta == ORIGEM_MODELO and not eval_resultado["passed"]:
            origem_resposta = ORIGEM_CONTINGENCIA
            erro_contingencia = "Resposta do modelo reprovada pelo filtro de vazamento."
            texto_final = "Não consegui confirmar uma resposta segura agora. Tente novamente."
            provedor_executado = None
            modelo_executado = None

        retorno = {
            "sucesso": origem_resposta == ORIGEM_MODELO,
            "origem_resposta": origem_resposta,
            "resposta": texto_final,
            "categoria_negociada": {
                "id": detalhes_cat.get("id"),
                "chave": chave_cat,
                "nome": detalhes_cat.get("nome"),
            },
            "protocolo_negociacao": {
                "provedor_utilizado": provedor_executado,
                "modelo_utilizado": modelo_executado,
                "provedores_alternativos_homologados": provedores_alt,
                "sla_latencia_max_ms": negociacao_cfg.get("sla_latencia_max_ms", 1000),
            },
            "temporalidade": {
                "data_corte_fixa": cls.DATA_CORTE_FIXA,
                "horario_casado": horario_casado,
                "timestamp_completo": f"{cls.DATA_CORTE_FIXA} {horario_casado}",
            },
            "eval_harness": eval_resultado,
        }
        if erro_contingencia is not None:
            retorno["erro"] = _sem_chave_no_texto(erro_contingencia)
        return retorno


def _sem_chave_no_texto(texto: str) -> str:
    """Garante que a mensagem de erro devolvida ao cliente HTTP não contém a chave."""
    chave = obter_api_key()[0]
    texto = str(texto)
    if chave and chave in texto:
        texto = texto.replace(chave, "***")
    return texto
