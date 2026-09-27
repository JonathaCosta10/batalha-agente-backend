"""GET conversas/status/: modelo configurado x observado, orçamento, limites; nunca texto nem identificador."""
import json
import unittest
from unittest import mock

import conversas_apoio  # noqa: F401 -- configura o Django

from django.test import Client, override_settings

from apps.conversas import views
from apps.conversas.gateway import GeminiGateway
from apps.conversas.service import ConversationService

URL = '/api/v1/context-agent/conversas/status/'


class StatusHarness(unittest.TestCase):
    def test_sem_chamada_diz_nao_medido(self):
        with mock.patch.object(views, 'get_service', return_value=ConversationService(gateway=GeminiGateway())):
            r = Client().get(URL)
        body = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(body['model_version_observado'].startswith('NAO_MEDIDO'))
        self.assertEqual(body['orcamento_processo']['usadas'], 0)
        self.assertTrue(body['cota_diaria_provedor'].startswith('NAO_MEDIDO'))

    def test_model_version_vem_da_metrica_e_sem_texto(self):
        gw = GeminiGateway()
        gw.calls = 3
        gw.metrics.append({'stage': 'generate', 'model': 'gemini-3.5-flash-lite', 'model_version': 'gemini-3.5-flash-lite-001',
                           'prompt_sha256': 'a' * 64, 'latency_ms': 700, 'outcome': 'complete', 'total_tokens': 900,
                           'texto_que_nao_pode_sair': 'Maria 00108ccd'})
        with mock.patch.object(views, 'get_service', return_value=ConversationService(gateway=gw)):
            body = Client().get(URL).json()
        self.assertEqual(body['model_version_observado'], 'gemini-3.5-flash-lite-001')
        self.assertEqual(body['orcamento_processo']['restantes'], gw.max_calls - 3)
        cru = json.dumps(body, ensure_ascii=False)
        self.assertNotIn('Maria', cru)          # prova negativa: campo fora da lista branca não vaza
        self.assertNotIn('prompt_sha256', cru)

    def test_modo_demo_sem_gateway(self):
        with mock.patch.object(views, 'get_service', return_value=ConversationService()):
            body = Client().get(URL).json()
        self.assertIsNone(body['orcamento_processo'])
        self.assertIsNone(body['modelo_configurado'])

    def test_post_e_405(self):
        self.assertEqual(Client().post(URL).status_code, 405)


if __name__ == '__main__':
    unittest.main()
