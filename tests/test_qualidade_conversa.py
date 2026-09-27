"""Medição honesta: texto plausível não vira groundedness sem evidências."""

import json
import os
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")
import django  # noqa: E402

django.setup()
from django.test import Client, SimpleTestCase

from apps.context_agent_datadriven.pastas_raiz.controles_evals.evals_google_agent import executar_eval_harness


class AvaliacaoHonestaTest(SimpleTestCase):
    def test_prova_negativa_resposta_sem_evidencia_nao_e_aprovada(self):
        # Mesmo uma resposta fluente não tem prova factual se nenhuma fonte foi comparada.
        resultado = executar_eval_harness("Seu saldo dobrou neste mês.", "16:28:44")
        self.assertIsNone(resultado["groundedness_score"])
        self.assertEqual(resultado["eval_status"], "NAO_MEDIDO")
        self.assertEqual(resultado["temporal_validation"], "NAO_MEDIDO")

    def test_filtro_mecanico_reprova_vazamento(self):
        resultado = executar_eval_harness("score: 187", "16:28:44")
        self.assertFalse(resultado["passed"])
        self.assertEqual(resultado["eval_status"], "REPROVADO_VAZAMENTO")
        self.assertFalse(resultado["controles_mecanicos"]["vazamento_score_aprovado"])

    @patch("apps.context_agent_datadriven.views.chamar_gemini")
    def test_primeira_chamada_mede_tempo_sem_alterar_payload_google(self, chamar):
        chamar.return_value = {"sucesso": True, "modelo": "gemini-2.5-flash-lite", "resposta": "Olá!"}
        resposta = Client().post(
            "/api/v1/context-agent/primeira-chamada/",
            data=json.dumps({"texto_inicial": "Olá"}), content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(chamar.call_args.args, ("Olá",))
        self.assertGreaterEqual(resposta.json()["tempo_resposta_ms"], 0)

    def test_entrada_invalida_tambem_mede_tempo(self):
        resposta = Client().post(
            "/api/v1/context-agent/primeira-chamada/",
            data=json.dumps({"texto_inicial": ""}), content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertGreaterEqual(resposta.json()["tempo_resposta_ms"], 0)
