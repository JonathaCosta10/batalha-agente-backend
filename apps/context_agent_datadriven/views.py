"""
Views e Endpoints REST do aplicativo context-agent-datadriven.
Implementa a arquitetura de Harness com:
- Base de rotas mapeada em template .yaml
- Agente distribuidor de chamadas conforme protocolo de negociação (agentes/agente.py)
- LLM_Models (google, antropic, openIa)
- Pastas raiz de evidências e evals
"""

from time import perf_counter

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse
from django.views import View

from .rotas.manager import BaseDeRotasManager
from .agentes.agente import AgenteNegotiatorEngine
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

ROTA_SUBSTITUTA = "/api/v1/context-agent/conversas/interacao/"


class EnviarMensagemHarnessAPI(APIView):
    """
    Rota descontinuada (Decisão D-3, 2026-09-27): o front usa só conversas/interacao/.
    Qualquer método responde 410 Gone apontando a rota nova, sem ler o corpo, sem gravar
    sessão e sem chamar modelo. Resolve I1 (cliente demo "Eduarda" atendendo a pessoa real)
    e I9 (chave na URL). A implementação anterior está em
    archive/2026-09-27/apps/context_agent_datadriven/views.py.
    """
    CORPO = {"erro": "rota_descontinuada", "usar": ROTA_SUBSTITUTA}

    def _gone(self, request, *args, **kwargs):
        return Response(dict(self.CORPO), status=status.HTTP_410_GONE)

    get = post = put = patch = delete = _gone


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
