"""Primeira chamada Gemini: apenas o texto inicial compõe a carga enviada."""

import json
import urllib.error
import urllib.request

from desafio_itau.modelos_llm import MODELO_PRIMEIRA_CHAMADA
from desafio_itau.segredos import obter_api_key


MODELO = MODELO_PRIMEIRA_CHAMADA


def chamar_gemini(texto_inicial: str) -> dict:
    chave, _origem = obter_api_key()
    if not chave:
        return {"sucesso": False, "erro": "Defina API_KEY_SECRECT no arquivo .secrets da raiz da solução."}

    carga = {"contents": [{"role": "user", "parts": [{"text": texto_inicial}]}]}
    requisicao = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent",
        data=json.dumps(carga).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": chave},
        method="POST",
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=20) as resposta:
            dados = json.load(resposta)
    except urllib.error.HTTPError as erro:
        return {"sucesso": False, "erro": f"Google API respondeu HTTP {erro.code}. Confira a chave, o modelo e a cota do projeto."}
    except urllib.error.URLError:
        return {"sucesso": False, "erro": "Não foi possível conectar à Google API."}
    except (TimeoutError, ValueError):
        return {"sucesso": False, "erro": "A Google API não devolveu uma resposta válida a tempo."}

    candidatos = dados.get("candidates") or []
    partes = candidatos[0].get("content", {}).get("parts", []) if candidatos else []
    texto = "".join(parte.get("text", "") for parte in partes).strip()
    if not texto:
        return {"sucesso": False, "erro": "O modelo não devolveu texto."}
    return {"sucesso": True, "modelo": MODELO, "resposta": texto}
