"""
Serviço de Comunicação com o Agente via Secret do gsconsole (Google Cloud / AI Studio).
Projeto: desafio-itau-batalha-de-agentes-time2
App: context-agent-datadriven
"""

import urllib.request
import urllib.error
from typing import Dict, Any, Optional

from desafio_itau.modelos_llm import MODELOS_GOOGLE
from desafio_itau.segredos import obter_api_key

class AgenteSecretService:
    """
    Gerencia a comunicação segura com o Agente utilizando o Secret configurado
    no gsconsole (Google Cloud Console / AI Studio Secret Manager).
    """

    # Modelos suportados na chave gsconsole
    MODELOS_PRIORITARIOS = MODELOS_GOOGLE

    @classmethod
    def get_gsconsole_secret(cls) -> Optional[str]:
        """
        Recupera o Secret configurado no gsconsole.
        Ordem definida em desafio_itau.segredos.obter_api_key:
        env API_KEY_SECRECT > .secrets:API_KEY_SECRECT > GEMINI_API_KEY / GSCONSOLE_SECRET / GOOGLE_API_KEY
        """
        return obter_api_key()[0]

    # Estados da chave. Sem chamada de rede só se sabe se ela existe:
    STATUS_AUSENTE = "AUSENTE"          # nenhuma chave encontrada
    STATUS_CONFIGURADA = "CONFIGURADA"  # existe, mas NÃO foi testada contra a Google
    # Com ?validar=1 (uma chamada GET barata à Google):
    STATUS_VALIDADA = "VALIDADA"        # a Google aceitou a chave (HTTP 200)
    STATUS_INVALIDA = "INVALIDA"        # a Google recusou a chave (HTTP 400/401/403)
    STATUS_NAO_MEDIDO = "NAO_MEDIDO"    # pediu-se validação mas não se conseguiu medir

    URL_VALIDACAO = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1"
    TIMEOUT_VALIDACAO_S = 5

    @staticmethod
    def _mascarar(secret: str) -> str:
        """Nunca devolve a chave: 6+4 caracteres só quando sobram pelo menos 10 ocultos."""
        if len(secret) >= 20:
            return f"{secret[:6]}...{secret[-4:]}"
        return f"*** ({len(secret)} caracteres)"

    @classmethod
    def validar_chave_na_google(cls, secret: str) -> Dict[str, Any]:
        """
        Uma chamada barata (lista 1 modelo) com a chave no header x-goog-api-key,
        nunca na URL. Devolve {status, http_status, detalhe}; erro de rede ou
        resposta ambígua (429, 5xx) = NAO_MEDIDO, dito como tal.
        """
        req = urllib.request.Request(
            cls.URL_VALIDACAO,
            headers={"x-goog-api-key": secret},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=cls.TIMEOUT_VALIDACAO_S) as resposta:
                codigo = getattr(resposta, "status", 200)
        except urllib.error.HTTPError as erro:
            if erro.code in (400, 401, 403):
                return {"status": cls.STATUS_INVALIDA, "http_status": erro.code,
                        "detalhe": f"A Google recusou a chave (HTTP {erro.code})."}
            return {"status": cls.STATUS_NAO_MEDIDO, "http_status": erro.code,
                    "detalhe": f"A Google respondeu HTTP {erro.code}; isso não diz se a chave é válida."}
        except (urllib.error.URLError, TimeoutError, OSError) as erro:
            motivo = getattr(erro, "reason", erro)
            return {"status": cls.STATUS_NAO_MEDIDO, "http_status": None,
                    "detalhe": f"Não foi possível contactar a Google ({type(motivo).__name__}); a chave não foi medida."}
        if codigo == 200:
            return {"status": cls.STATUS_VALIDADA, "http_status": 200,
                    "detalhe": "A Google aceitou a chave (GET /v1beta/models)."}
        return {"status": cls.STATUS_NAO_MEDIDO, "http_status": codigo,
                "detalhe": f"Resposta inesperada HTTP {codigo}; a chave não foi medida."}

    @classmethod
    def verificar_status_secret(cls, validar: bool = False) -> Dict[str, Any]:
        """
        Estado da credencial (sem expor a chave).
        validar=False: nenhuma chamada de rede -> AUSENTE | CONFIGURADA.
        validar=True e chave presente: GET barato à Google -> VALIDADA | INVALIDA | NAO_MEDIDO.
        """
        secret, origem = obter_api_key()
        presente = bool(secret)

        if not presente:
            status_chave = cls.STATUS_AUSENTE
            validacao = {"solicitada": validar, "executada": False, "http_status": None,
                         "detalhe": "Sem chave: nada a validar." if validar else "Validação não pedida (use ?validar=1)."}
        elif not validar:
            status_chave = cls.STATUS_CONFIGURADA
            validacao = {"solicitada": False, "executada": False, "http_status": None,
                         "detalhe": "Chave presente, não testada contra a Google (use ?validar=1)."}
        else:
            medida = cls.validar_chave_na_google(secret)
            status_chave = medida["status"]
            validacao = {"solicitada": True, "executada": True,
                         "http_status": medida["http_status"], "detalhe": medida["detalhe"]}

        return {
            "status": status_chave,
            "validacao": validacao,
            "origem": "Google Cloud Console Secret Manager (gsconsole)",
            "variavel_identificada": origem if presente else None,
            "secret_mascarado": cls._mascarar(secret) if presente else "NÃO_CONFIGURADO",
            "modelo_padrao": "gemini-flash-latest",
            "modelos_disponiveis": cls.MODELOS_PRIORITARIOS,
            "capacidade": "MAJOR_CAPABILITY_SERVER_SIDE_GEMINI_API",
        }

    # enviar_mensagem_agente saiu na Decisão D-3, 2026-09-27 (rota enviar-mensagem/ descontinuada, 410):
    # não tinha chamador e mandava a chave na URL (?key=). Original em
    # archive/2026-09-27/apps/context_agent_datadriven/services/agente_service.py.
