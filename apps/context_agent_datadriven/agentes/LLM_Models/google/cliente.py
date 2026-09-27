"""
Provedor Google LLM (AI Studio / gsconsole Secret)
Parte da arquitetura LLM_Models dentro da pasta Agentes.
"""

import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional

from desafio_itau.modelos_llm import MODELOS_GOOGLE
from desafio_itau.segredos import obter_api_key

class GoogleLLMCliente:
    """Cliente para modelos Google Gemini homologados na conta do agente via gsconsole."""

    PROVIDER_NAME = "google"
    MODELOS = MODELOS_GOOGLE

    @classmethod
    def get_secret(cls) -> Optional[str]:
        return obter_api_key()[0]

    @classmethod
    def executar_chamada(
        cls,
        modelo: str,
        system_instruction: str,
        contents: List[Dict[str, Any]],
        temperatura: float = 0.35,
        max_tokens: int = 650,
    ) -> Dict[str, Any]:
        secret = cls.get_secret()
        if not secret:
            return {
                "sucesso": False,
                "erro": "API_KEY_SECRECT não configurada para o provedor Google (arquivo .secrets da raiz).",
            }

        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": contents,
            "generationConfig": {
                "temperature": temperatura,
                "maxOutputTokens": max_tokens,
            }
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        # I9 / Decisão D-3, 2026-09-27: a chave vai no header x-goog-api-key, nunca na URL
        # (URL aparece em log, proxy e mensagem de exceção).
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
        req = urllib.request.Request(
            url, data=data_bytes,
            headers={"Content-Type": "application/json", "x-goog-api-key": secret},
        )

        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                if response.status == 200:
                    res_json = json.loads(response.read().decode("utf-8"))
                    candidates = res_json.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        texto = "".join([p.get("text", "") for p in parts]).strip()
                        return {
                            "sucesso": True,
                            "resposta": texto,
                            "provider": cls.PROVIDER_NAME,
                            "modelo": modelo,
                        }
        except Exception as e:
            return {
                "sucesso": False,
                "erro": str(e),
                "provider": cls.PROVIDER_NAME,
            }

        return {"sucesso": False, "erro": "Resposta vazia do provedor Google."}
