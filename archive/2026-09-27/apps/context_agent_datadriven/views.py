"""
Views e Endpoints REST do aplicativo context-agent-datadriven.
Implementa a arquitetura de Harness com:
- Base de rotas mapeada em template .yaml
- Agente distribuidor de chamadas conforme protocolo de negociação (agentes/agente.py)
- LLM_Models (google, antropic, openIa)
- Pastas raiz de evidências e evals
"""

import re
from time import perf_counter

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse
from django.views import View

from .models import ConversaAgenteSessao, MensagemAgenteRegistro
from .rotas.manager import BaseDeRotasManager
from .agentes.agente import AgenteNegotiatorEngine, ORIGEM_MODELO
from .agentes.LLM_Models import PROVEDORES_REGISTRADOS
from .pastas_raiz.docs.tese_agente_docs import TESE_COMPLETA_CONTEXTUALIZADA
from .pastas_raiz.controles_evals.evals_google_agent import EVAL_METRICAS_MERCADO
from .services.agente_service import AgenteSecretService
from .services.primeira_chamada import chamar_gemini
from .templates.context_agent_painel_html import HTML_PAINEL

class StatusHarnessAPI(APIView):
    """Retorna a auditoria mecânica das rotas YAML, modelos LLM_Models e protocolo de negociação."""
    VALORES_VALIDAR = {"1", "true", "sim"}

    def get(self, request):
        rotas = BaseDeRotasManager.carregar_rotas()
        # Sem ?validar=1 não há chamada de rede: o estado é AUSENTE/CONFIGURADA.
        validar = str(request.GET.get("validar", "")).strip().lower() in self.VALORES_VALIDAR
        secret_status = AgenteSecretService.verificar_status_secret(validar=validar)
        
        return Response({
            "app": "context-agent-datadriven",
            "arquitetura": "Harness com Base de Rotas YAML e Protocolo de Negociação",
            "base_de_rotas": {
                "template": "rotas/templates/rotas_base.yaml",
                "versao_schema": rotas.get("versao_schema"),
                "total_categorias": len(rotas.get("categorias", {})),
                "categorias": rotas.get("categorias"),
            },
            "agente_distribuidor": {
                "modulo": "agentes/agente.py",
                "funcao": "distribuir_chamada (Protocolo de Negociação)",
                "data_corte_fixa": AgenteNegotiatorEngine.DATA_CORTE_FIXA,
            },
            "llm_models_provedores": {
                "pastas_registradas": list(PROVEDORES_REGISTRADOS.keys()), # google, antropic, openIa
                "secret_gsconsole": secret_status,
            },
            "pastas_raiz": {
                "docs": {
                    "versao_tese": TESE_COMPLETA_CONTEXTUALIZADA["versao_tese"],
                    "fontes_evidencia": len(TESE_COMPLETA_CONTEXTUALIZADA["fontes_de_evidencia"]),
                },
                "controles_e_evals": EVAL_METRICAS_MERCADO,
            }
        }, status=status.HTTP_200_OK)

class EnviarMensagemHarnessAPI(APIView):
    """
    Endpoint principal acionado pela Fase 3 (Novo Chat):
    - Models aponta para a base de rotas YAML
    - Agente distribui chamada conforme o protocolo de negociação
    - Temporalidade casada em 22/12/2025
    - Dados brutos permanecem sigilosos internamente
    """
    def post(self, request):
        inicio = perf_counter()
        dados, erro = validar_corpo_enviar_mensagem(request.data)
        if erro:
            return Response({"erro": erro, "tempo_resposta_ms": round((perf_counter() - inicio) * 1000, 3)},
                            status=status.HTTP_400_BAD_REQUEST)

        mensagem = dados["mensagem"]
        cliente_id = dados["cliente_id"]
        cliente_nome = dados["cliente_nome"]
        contexto_interno = dados["contexto"]

        sessao, _ = ConversaAgenteSessao.objects.get_or_create(
            cliente_id=cliente_id,
            defaults={
                "cliente_nome": cliente_nome,
                "score_comportamental": contexto_interno.get("score", 750),
                "indice_corte": contexto_interno.get("indice_corte", "CTX-750-ALPHA"),
                "data_corte_fixa": AgenteNegotiatorEngine.DATA_CORTE_FIXA,
                "horario_casado": AgenteNegotiatorEngine.calcular_horario_casado(cliente_id),
            }
        )

        resultado = sessao.despachar_chamada_harness(
            mensagem_usuario=mensagem,
            contexto_interno=contexto_interno,
        )

        corpo = {
            "sessao_id": sessao.id,
            "cliente_id": cliente_id,
            "mensagem_enviada": mensagem,
            "resposta_agente": resultado.get("resposta"),
            "origem_resposta": resultado["origem_resposta"],
            "categoria_negociada": resultado.get("categoria_negociada"),
            "protocolo_negociacao": resultado.get("protocolo_negociacao"),
            "temporalidade": resultado.get("temporalidade"),
            "eval_harness": resultado.get("eval_harness"),
            "sucesso": resultado["sucesso"],
            "tempo_resposta_ms": round((perf_counter() - inicio) * 1000, 3),
        }
        if resultado["origem_resposta"] != ORIGEM_MODELO:
            # Nenhum modelo respondeu: 503, como a primeira-chamada. O texto de
            # contingência segue em resposta_agente, rotulado por origem_resposta.
            corpo["erro"] = resultado.get("erro") or "Nenhum modelo respondeu."
            return Response(corpo, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(corpo, status=status.HTTP_200_OK)


def _e_numero(valor) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def validar_corpo_enviar_mensagem(dados_brutos):
    """
    Valida o corpo do POST enviar-mensagem. Devolve (dados, None) ou (None, erro).
    Tipos errados passam a dar 400 {erro}; antes levantavam exceção (HTTP 500).
    """
    if not isinstance(dados_brutos, dict):
        return None, "Envie um objeto JSON com o campo 'mensagem'."

    mensagem = dados_brutos.get("mensagem")
    if mensagem is None:
        return None, "O campo 'mensagem' é obrigatório."
    if not isinstance(mensagem, str):
        return None, "O campo 'mensagem' deve ser texto."
    mensagem = mensagem.strip()
    if not mensagem:
        return None, "O campo 'mensagem' é obrigatório."

    cliente_id = dados_brutos.get("cliente_id", 42)
    if isinstance(cliente_id, str) and re.fullmatch(r"\s*[+-]?[0-9]+\s*", cliente_id):
        cliente_id = int(cliente_id)
    if isinstance(cliente_id, bool) or not isinstance(cliente_id, int):
        return None, "O campo 'cliente_id' deve ser um número inteiro."

    cliente_nome = dados_brutos.get("cliente_nome", "Cliente Itaú")
    if not isinstance(cliente_nome, str):
        return None, "O campo 'cliente_nome' deve ser texto."

    for campo in ("indice_corte", "segmento"):
        if campo in dados_brutos and not isinstance(dados_brutos[campo], str):
            return None, f"O campo '{campo}' deve ser texto."
    if "score" in dados_brutos and not _e_numero(dados_brutos["score"]):
        return None, "O campo 'score' deve ser número."

    if "contexto" in dados_brutos:
        contexto = dados_brutos["contexto"]
        if not isinstance(contexto, dict):
            return None, "O campo 'contexto' deve ser um objeto JSON."
        if "score" in contexto and not _e_numero(contexto["score"]):
            return None, "O campo 'contexto.score' deve ser número."
        for campo in ("nome", "indice_corte", "segmento"):
            if campo in contexto and not isinstance(contexto[campo], str):
                return None, f"O campo 'contexto.{campo}' deve ser texto."
    else:
        contexto = {
            "id": cliente_id,
            "nome": cliente_nome,
            "score": dados_brutos.get("score", 750),
            "indice_corte": dados_brutos.get("indice_corte", "CTX-750-ALPHA"),
            "segmento": dados_brutos.get("segmento", "Itaú Uniclass"),
        }

    return {"mensagem": mensagem, "cliente_id": cliente_id,
            "cliente_nome": cliente_nome, "contexto": contexto}, None


class PainelAgenteView(View):
    """Painel HTML do context-agent-datadriven."""
    def get(self, request):
        # Estado da chave sem chamada de rede (AUSENTE / CONFIGURADA): o painel
        # não afirma que a chave funciona, porque não mediu.
        estado = AgenteSecretService.verificar_status_secret(validar=False)["status"]
        return HttpResponse(HTML_PAINEL.replace("{{ESTADO_CHAVE}}", estado), content_type="text/html")


class PrimeiraChamadaAPI(APIView):
    """Uma mensagem de texto, sem histórico nem dados do cliente na carga Gemini."""

    def post(self, request):
        inicio = perf_counter()
        if not isinstance(request.data, dict) or set(request.data) != {"texto_inicial"}:
            return Response({"erro": "Envie somente texto_inicial.", "tempo_resposta_ms": round((perf_counter() - inicio) * 1000, 3)}, status=status.HTTP_400_BAD_REQUEST)
        texto = request.data.get("texto_inicial")
        if not isinstance(texto, str) or not texto.strip():
            return Response({"erro": "Informe texto_inicial.", "tempo_resposta_ms": round((perf_counter() - inicio) * 1000, 3)}, status=status.HTTP_400_BAD_REQUEST)
        texto = texto.strip()
        if len(texto) > 2000:
            return Response({"erro": "O texto inicial deve ter no máximo 2000 caracteres.", "tempo_resposta_ms": round((perf_counter() - inicio) * 1000, 3)}, status=status.HTTP_400_BAD_REQUEST)

        resultado = chamar_gemini(texto)
        if not resultado["sucesso"]:
            return Response({"erro": resultado["erro"], "tempo_resposta_ms": round((perf_counter() - inicio) * 1000, 3)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({**resultado, "tempo_resposta_ms": round((perf_counter() - inicio) * 1000, 3)}, status=status.HTTP_200_OK)
