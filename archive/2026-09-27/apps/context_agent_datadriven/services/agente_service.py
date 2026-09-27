"""
Serviço de Comunicação com o Agente via Secret do gsconsole (Google Cloud / AI Studio).
Projeto: desafio-itau-batalha-de-agentes-time2
App: context-agent-datadriven
"""

import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional

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

    @classmethod
    def enviar_mensagem_agente(
        cls,
        mensagem_usuario: str,
        contexto_cliente: Optional[Dict[str, Any]] = None,
        historico_mensagens: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Envia a mensagem ao Agente orientada pelos dados comportamentais do cliente
        e recebe a resposta processada via Secret do gsconsole.
        """
        secret = cls.get_gsconsole_secret()
        if not secret:
            return {
                "sucesso": False,
                "erro": "API_KEY_SECRECT não configurada (arquivo .secrets da raiz ou ambiente).",
                "resposta": "Erro: chave do agente não configurada. Defina API_KEY_SECRECT no arquivo .secrets da raiz da solução.",
            }

        # Constrói o Prompt de Sistema com a contextualização orientada a dados
        cliente_info = contexto_cliente or {
            "id": 42,
            "nome": "Cliente Itaú",
            "genero": "F",
            "score": 750,
            "indice_corte": "CTX-750-ALPHA",
            "segmento": "Itaú Uniclass",
        }

        system_instruction = (
            f"Você é o Agente Especialista do Itaú (Time 2 - Batalha de Agentes).\n"
            f"Você está atendendo o cliente {cliente_info.get('nome')} (ID #{cliente_info.get('id')}).\n"
            f"Perfil comportamental: Score {cliente_info.get('score')}/1000 | "
            f"Índice de Corte: {cliente_info.get('indice_corte')} | "
            f"Segmento: {cliente_info.get('segmento')}.\n"
            f"Diretriz: Seja consultivo, transparente, acolhedor e foque em equilíbrio financeiro e produtos Itaú adequados."
        )

        # Montagem dos contents da API
        contents = []

        # Adiciona histórico se houver
        if historico_mensagens:
            for item in historico_mensagens:
                papel = "user" if item.get("papel") in ["user", "usuario"] else "model"
                contents.append({
                    "role": papel,
                    "parts": [{"text": item.get("conteudo", "")}]
                })

        # Adiciona mensagem atual
        contents.append({
            "role": "user",
            "parts": [{"text": mensagem_usuario}]
        })

        payload = {
            "system_instruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 800,
            }
        }

        data = json.dumps(payload).encode("utf-8")
        ultimo_erro = None

        # Tenta os modelos prioritários (gemini-flash-latest com melhor cota e latência)
        for modelo in cls.MODELOS_PRIORITARIOS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={secret}"
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"}
            )

            try:
                with urllib.request.urlopen(req, timeout=15) as response:
                    if response.status == 200:
                        resp_json = json.loads(response.read().decode("utf-8"))
                        candidates = resp_json.get("candidates", [])
                        if candidates and "content" in candidates[0]:
                            parts = candidates[0]["content"].get("parts", [])
                            resposta_texto = "".join([p.get("text", "") for p in parts])
                            return {
                                "sucesso": True,
                                "resposta": resposta_texto.strip(),
                                "modelo": modelo,
                                "secret_status": "VALIDADO_GSCONSOLE",
                                "contexto_utilizado": {
                                    "cliente_id": cliente_info.get("id"),
                                    "cliente_nome": cliente_info.get("nome"),
                                    "score": cliente_info.get("score"),
                                    "indice": cliente_info.get("indice_corte"),
                                },
                            }
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                ultimo_erro = f"HTTP {e.code}: {e.reason}"
                continue
            except Exception as e:
                ultimo_erro = str(e)
                continue

        return {
            "sucesso": False,
            "erro": ultimo_erro or "Falha na comunicação com o Agente",
            "resposta": f"Não foi possível receber resposta do Agente no momento ({ultimo_erro}). Verifique o Secret do gsconsole.",
        }
