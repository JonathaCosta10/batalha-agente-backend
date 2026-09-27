"""Decisão D-5, 2026-09-27: CORS e CSRF aceitam o front em localhost e 127.0.0.1, portas 3000 e 3001.

Prova negativa: a porta 3002 (e outro host) não entram, nem no CORS nem no CSRF.
O CSRF é conferido pelo próprio CsrfViewMiddleware do Django (a mesma checagem de Origin que as views de
apps/conversas aplicam localmente); o CORS, por um preflight real pelo test client.
"""

import os
import unittest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")
import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.middleware.csrf import CsrfViewMiddleware  # noqa: E402
from django.test import Client, RequestFactory  # noqa: E402

ACEITAS = [f"http://{h}:{p}" for p in (3000, 3001) for h in ("localhost", "127.0.0.1")]
RECUSADAS = ["http://localhost:3002", "http://127.0.0.1:3002", "http://evil.example:3000"]
URL = "/api/v1/context-agent/status-harness/"


def origem_csrf_aceita(origem: str) -> bool:
    request = RequestFactory().post("/qualquer/", HTTP_ORIGIN=origem)
    return CsrfViewMiddleware(lambda r: None)._origin_verified(request)


def origem_cors_aceita(origem: str) -> bool:
    r = Client().options(URL, HTTP_ORIGIN=origem, HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST")
    return r.headers.get("access-control-allow-origin") in (origem, "*")  # "*" (CORS aberto) também é aceite


class OrigensDoFrontTest(unittest.TestCase):
    def test_configuracao_tem_as_duas_portas_nos_dois_hosts(self):
        self.assertEqual(sorted(settings.CSRF_TRUSTED_ORIGINS), sorted(ACEITAS))
        self.assertEqual(sorted(settings.CORS_ALLOWED_ORIGINS), sorted(ACEITAS))
        self.assertFalse(settings.CORS_ALLOW_ALL_ORIGINS)

    def test_csrf_aceita_3000_e_3001(self):
        for origem in ACEITAS:
            with self.subTest(origem=origem):
                self.assertTrue(origem_csrf_aceita(origem))

    def test_cors_aceita_3000_e_3001(self):
        for origem in ACEITAS:
            with self.subTest(origem=origem):
                self.assertTrue(origem_cors_aceita(origem))

    def test_prova_negativa_3002_nao_entra(self):
        for origem in RECUSADAS:
            with self.subTest(origem=origem):
                self.assertFalse(origem_csrf_aceita(origem), f"CSRF aceitou {origem}")
                self.assertFalse(origem_cors_aceita(origem), f"CORS aceitou {origem}")


if __name__ == "__main__":
    unittest.main()
