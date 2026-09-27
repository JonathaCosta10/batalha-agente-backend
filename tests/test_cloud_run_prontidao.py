"""Prontidão para o Cloud Run (2026-09-27): settings lidos do ambiente e GET /healthz.

O deploy NÃO é feito aqui (é a etapa final, depois do OK do Henrique; docs/decisoes-e-logica-2026-09-27.md §5).

- Settings de produção são conferidos num subprocesso novo, porque o settings.py só é lido uma vez por processo.
  Prova negativa: DJANGO_DEBUG=0 sem DJANGO_SECRET_KEY -> o app recusa subir (ImproperlyConfigured). Controle
  positivo: a mesma chamada COM a chave sobe, para provar que a recusa vem da chave e não de outra coisa.
- /healthz responde 200 {"status": "ok"} com a rede bloqueada (socket) e sem nenhuma consulta ao banco. Prova
  negativa: com o mesmo Host fora de ALLOWED_HOSTS, uma rota comum recebe 400; só o /healthz passa.
"""

import json
import os
import socket
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")
import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from django.test import Client, override_settings  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
VARIAVEIS_DE_PRODUCAO = (
    "DJANGO_DEBUG", "DEBUG", "DJANGO_SECRET_KEY", "SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "ALLOWED_HOSTS",
    "DJANGO_CSRF_TRUSTED_ORIGINS", "CSRF_TRUSTED_ORIGINS",
)
SONDA = (
    "import json, django; django.setup(); from django.conf import settings as s; "
    "print(json.dumps({'DEBUG': s.DEBUG, 'ALLOWED_HOSTS': s.ALLOWED_HOSTS, "
    "'SECURE_PROXY_SSL_HEADER': list(getattr(s, 'SECURE_PROXY_SSL_HEADER', None) or []), "
    "'CSRF_TRUSTED_ORIGINS': s.CSRF_TRUSTED_ORIGINS, 'CHAVE_DEV': s.SECRET_KEY == s.SECRET_KEY_DESENVOLVIMENTO}))"
)


def subir(**variaveis):
    """Importa o settings num processo novo com só estas variáveis de produção. -> (returncode, stdout, stderr)."""
    env = {k: v for k, v in os.environ.items() if k not in VARIAVEIS_DE_PRODUCAO}
    env["DJANGO_SETTINGS_MODULE"] = "desafio_itau.settings"
    env.update(variaveis)
    r = subprocess.run([sys.executable, "-c", SONDA], cwd=str(RAIZ), env=env, capture_output=True, text=True,
                       timeout=120)
    return r.returncode, r.stdout.strip(), r.stderr


class SettingsDoAmbienteTest(unittest.TestCase):
    def test_prova_negativa_debug_0_sem_secret_key_recusa_subir(self):
        codigo, _, erro = subir(DJANGO_DEBUG="0")
        self.assertNotEqual(codigo, 0)
        self.assertIn("ImproperlyConfigured", erro)
        self.assertIn("DJANGO_SECRET_KEY", erro)

    def test_prova_negativa_debug_0_com_a_chave_de_desenvolvimento_recusa_subir(self):
        from django.conf import settings
        codigo, _, erro = subir(DJANGO_DEBUG="0", DJANGO_SECRET_KEY=settings.SECRET_KEY_DESENVOLVIMENTO)
        self.assertNotEqual(codigo, 0)
        self.assertIn("ImproperlyConfigured", erro)

    def test_controle_debug_0_com_secret_key_sobe(self):
        codigo, saida, erro = subir(DJANGO_DEBUG="0", DJANGO_SECRET_KEY="teste-" + "x" * 50)
        self.assertEqual(codigo, 0, erro)
        cfg = json.loads(saida)
        self.assertFalse(cfg["DEBUG"])
        self.assertFalse(cfg["CHAVE_DEV"])
        self.assertEqual(cfg["SECURE_PROXY_SSL_HEADER"], ["HTTP_X_FORWARDED_PROTO", "https"])

    def test_debug_0_allowed_hosts_vem_do_ambiente(self):
        codigo, saida, erro = subir(DJANGO_DEBUG="0", DJANGO_SECRET_KEY="teste-" + "x" * 50,
                                    DJANGO_ALLOWED_HOSTS="a.run.app, b.example.com")
        self.assertEqual(codigo, 0, erro)
        self.assertEqual(json.loads(saida)["ALLOWED_HOSTS"], ["a.run.app", "b.example.com"])

    def test_prova_negativa_debug_0_sem_allowed_hosts_nao_abre_para_todos(self):
        codigo, saida, erro = subir(DJANGO_DEBUG="0", DJANGO_SECRET_KEY="teste-" + "x" * 50)
        self.assertEqual(codigo, 0, erro)
        self.assertNotIn("*", json.loads(saida)["ALLOWED_HOSTS"])

    def test_local_sem_variaveis_mantem_o_comportamento_de_antes(self):
        codigo, saida, erro = subir()
        self.assertEqual(codigo, 0, erro)
        cfg = json.loads(saida)
        self.assertTrue(cfg["DEBUG"])
        self.assertEqual(cfg["ALLOWED_HOSTS"], ["*"])
        self.assertTrue(cfg["CHAVE_DEV"])
        self.assertEqual(cfg["SECURE_PROXY_SSL_HEADER"], [])

    def test_csrf_extra_do_ambiente_soma_as_origens_da_d5(self):
        codigo, saida, erro = subir(DJANGO_CSRF_TRUSTED_ORIGINS="https://i-agora-conversacional.example.run.app/")
        self.assertEqual(codigo, 0, erro)
        origens = json.loads(saida)["CSRF_TRUSTED_ORIGINS"]
        self.assertIn("https://i-agora-conversacional.example.run.app", origens)
        self.assertIn("http://localhost:3001", origens)


def _sem_rede(*_a, **_k):
    raise OSError("rede bloqueada pelo teste do /healthz")


class HealthzTest(unittest.TestCase):
    HOST_INTERNO = "10.0.0.7:8080"  # como uma sonda do Cloud Run: Host fora de ALLOWED_HOSTS

    def setUp(self):
        producao = override_settings(DEBUG=False, ALLOWED_HOSTS=["i-agora-conversacional.example.run.app"])
        producao.enable()
        self.addCleanup(producao.disable)

    def _get(self, caminho, host=None):
        with mock.patch.object(socket.socket, "connect", _sem_rede), \
                mock.patch.object(socket, "create_connection", _sem_rede), \
                CaptureQueriesContext(connection) as consultas:
            r = Client().get(caminho, HTTP_HOST=host or self.HOST_INTERNO)
        return r, len(consultas)

    def test_healthz_200_sem_rede_e_sem_banco(self):
        for caminho in ("/healthz", "/healthz/"):
            r, n_consultas = self._get(caminho)
            self.assertEqual(r.status_code, 200, caminho)
            self.assertEqual(r.json(), {"status": "ok"})
            self.assertEqual(n_consultas, 0)
            self.assertEqual(r["Cache-Control"], "no-store")

    def test_prova_negativa_rota_comum_com_o_mesmo_host_recebe_400(self):
        r, _ = self._get("/api/v1/context-agent/conversas/status/")
        self.assertEqual(r.status_code, 400)

    def test_prova_negativa_post_no_healthz_nao_e_atalho(self):
        r = Client().post("/healthz", HTTP_HOST="i-agora-conversacional.example.run.app")
        self.assertNotEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
