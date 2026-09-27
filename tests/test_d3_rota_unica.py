"""Decisão D-3, 2026-09-27: uma rota só (conversas/interacao/). enviar-mensagem/ responde 410 Gone.

Também I9: o cliente Google (agentes/LLM_Models/google/cliente.py), que segue vivo porque perfil_usuario
o usa, manda a chave no header x-goog-api-key e nunca na URL.
Provas negativas: o verificador de URL reprova uma URL com key=; a rota antiga não volta a ter a view nem
o código que só ela usava.
"""

import ast
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")
import django  # noqa: E402

django.setup()

from django.test import Client  # noqa: E402
from django.urls import resolve  # noqa: E402

from apps.context_agent_datadriven import models, views  # noqa: E402
from apps.context_agent_datadriven.agentes.LLM_Models.google.cliente import GoogleLLMCliente  # noqa: E402
from apps.context_agent_datadriven.services.agente_service import AgenteSecretService  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
URL_ANTIGA = "/api/v1/context-agent/enviar-mensagem/"
GONE = {"erro": "rota_descontinuada", "usar": "/api/v1/context-agent/conversas/interacao/"}
CHAVE = "AIzaSyTESTE-chave-falsa-0123456789abcd"
SEM_ARQUIVO = str(Path(tempfile.gettempdir()) / "nao-existe" / ".secrets")


def url_expoe_chave(url: str, chave: str) -> bool:
    return "key=" in url or chave in url


def urls_google_com_key(fonte: str) -> list:
    """Linhas com f-string que monta URL do Google com 'key=' (só literais de código, via AST)."""
    linhas = []
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.JoinedStr):
            texto = "".join(v.value for v in no.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
            if "generativelanguage" in texto and "key=" in texto:
                linhas.append(no.lineno)
    return linhas


class RespostaOk:
    status = 200

    def read(self):
        return json.dumps({"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class RotaAntigaTest(unittest.TestCase):
    def test_410_com_json_para_todo_metodo(self):
        c = Client()
        for metodo in ("get", "post", "put", "patch", "delete"):
            with self.subTest(metodo=metodo):
                if metodo == "get":
                    r = c.get(URL_ANTIGA)
                else:
                    r = getattr(c, metodo)(URL_ANTIGA, data=json.dumps({"mensagem": "oi"}), content_type="application/json")
                self.assertEqual(r.status_code, 410)
                self.assertEqual(r.json(), GONE)

    def test_a_rota_indicada_existe_e_e_da_conversa_nova(self):
        destino = resolve(GONE["usar"])  # Resolver404 se não existir
        self.assertTrue(destino.func.__module__.startswith("apps.conversas"), destino.func.__module__)

    def test_codigo_que_so_a_rota_usava_saiu_e_esta_no_archive(self):
        self.assertFalse(hasattr(views, "validar_corpo_enviar_mensagem"))
        self.assertFalse(hasattr(models.ConversaAgenteSessao, "despachar_chamada_harness"))
        self.assertFalse(hasattr(AgenteSecretService, "enviar_mensagem_agente"))
        arq = RAIZ / "archive" / "2026-09-27" / "apps" / "context_agent_datadriven"
        self.assertIn("def validar_corpo_enviar_mensagem", (arq / "views.py").read_text(encoding="utf-8"))
        self.assertIn("def despachar_chamada_harness", (arq / "models.py").read_text(encoding="utf-8"))
        self.assertIn("def enviar_mensagem_agente", (arq / "services" / "agente_service.py").read_text(encoding="utf-8"))


class ChaveForaDaUrlTest(unittest.TestCase):
    """I9: agentes/LLM_Models/google/cliente.py (antes :50 tinha ?key= na URL)."""

    def test_url_sem_key_e_chave_no_header(self):
        with mock.patch.dict(os.environ, {"API_KEY_SECRECT": CHAVE, "SECRETS_FILE": SEM_ARQUIVO}), \
                mock.patch("urllib.request.urlopen", return_value=RespostaOk()) as abrir:
            r = GoogleLLMCliente.executar_chamada("gemini-x", "sistema", [{"role": "user", "parts": [{"text": "oi"}]}])
        self.assertTrue(r["sucesso"], r)
        req = abrir.call_args.args[0]
        self.assertFalse(url_expoe_chave(req.full_url, CHAVE), req.full_url)
        self.assertEqual(req.get_header("X-goog-api-key"), CHAVE)

    def test_prova_negativa_verificador_reprova_url_com_key(self):
        self.assertTrue(url_expoe_chave(f"https://x/v1beta/models/m:generateContent?key={CHAVE}", CHAVE))

    def test_nenhum_codigo_vivo_monta_url_com_key(self):
        """Varre apps/ por AST (comentário e docstring não contam): f-string de URL do Google com 'key='."""
        achados = []
        for arq in (RAIZ / "apps").rglob("*.py"):
            achados += [f"{arq.relative_to(RAIZ)}:{n}" for n in urls_google_com_key(arq.read_text(encoding="utf-8"))]
        self.assertEqual(achados, [])

    def test_prova_negativa_varredura_ast_pega_fstring_e_ignora_comentario(self):
        ruim = 'u = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={s}"\n'
        comentario = '# antes: generativelanguage ...?key={secret}\n"""doc: generativelanguage ?key={x}"""\n'
        self.assertEqual(urls_google_com_key(ruim), [1])
        self.assertEqual(urls_google_com_key(comentario), [])


if __name__ == "__main__":
    unittest.main()
