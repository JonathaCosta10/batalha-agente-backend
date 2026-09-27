"""Regra corte_seguro_ate_surplus_15, sem rede. Provas negativas: subcategoria sem gasto não entra;
Livre não recebe corte; essencial nunca é candidata; margem que não cobre vira CORTE_INSUFICIENTE."""

import os
import unittest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")
import django  # noqa: E402

django.setup()

from django.test import Client  # noqa: E402

from apps.context_agent_datadriven.services.plano_proposta import apresentar, base_da_media, candidatas, montar_proposta  # noqa: E402

LINHAS = [
    {"macro": "Delivery", "subcategoria": "Delivery", "lancamentos": 30, "total": 11000.0, "gasto_mensal": 1000.0, "meses": 11},
    {"macro": "Restaurantes", "subcategoria": "Padaria", "lancamentos": 20, "total": 4400.0, "gasto_mensal": 400.0, "meses": 11},
    {"macro": "Lazer", "subcategoria": "Cinema", "lancamentos": 0, "total": 0.0, "gasto_mensal": 0.0, "meses": 11},
]


class PlanoPropostaTest(unittest.TestCase):
    def test_subcategoria_real_meta_e_corte(self):
        # inflow 10.000, surplus 1.000 -> precisa de 500 para 15 %
        p = montar_proposta({"inflow_mensal": 10000.0, "surplus_mensal": 1000.0}, LINHAS)
        self.assertEqual(p["estado"], "OK")
        [c] = p["compromissos"]
        self.assertEqual((c["subcategoria"], c["gasto_atual"], c["corte"], c["meta"]), ("Delivery", 1000.0, 500.0, 500.0))
        self.assertEqual(c["texto"], "Limitar Delivery a R$ 500,00 em janeiro.")
        self.assertEqual(p["totais"]["valor_liberado"], 500.0)

    def test_nivel_2_corta_so_metade(self):
        [padaria] = [c for c in candidatas(LINHAS) if c["subcategoria"] == "Padaria"]
        self.assertEqual(padaria["margem"], 200.0)

    # --- provas negativas ---
    def test_sem_gasto_nao_entra(self):
        self.assertNotIn("Cinema", [c["subcategoria"] for c in candidatas(LINHAS)])

    def test_livre_nao_recebe_corte_e_ganha_reserva(self):
        p = montar_proposta({"inflow_mensal": 10000.0, "surplus_mensal": 3000.0}, LINHAS)
        self.assertEqual((p["estado"], p["compromissos"], p["totais"]["reserva"]), ("LIVRE_SEM_CORTE", [], 2000.0))

    def test_margem_insuficiente(self):
        p = montar_proposta({"inflow_mensal": 8828.12, "surplus_mensal": -1962.31}, LINHAS)
        self.assertEqual(p["estado"], "CORTE_INSUFICIENTE")
        self.assertGreater(p["totais"]["falta_apos_cortes"], 0)
        self.assertEqual(p["compromissos"][0]["texto"], "Pausar Delivery em janeiro (economia de R$ 1.000,00).")

    def test_essencial_nunca_e_candidata(self):
        mercado = [{"macro": "Mercado", "subcategoria": "Mercado", "lancamentos": 9, "total": 9.0, "gasto_mensal": 900.0, "meses": 11}]
        self.assertEqual(candidatas(mercado), [])  # nível 3: margem 0

    def test_apresentacao_linha_de_corte(self):
        linhas = [dict(l, base_inicio=202501, base_fim=202511) for l in LINHAS]
        p = montar_proposta({"inflow_mensal": 10000.0, "surplus_mensal": 1000.0}, linhas)
        p = apresentar(p, "2025-12-22", base_da_media(linhas), {("Delivery", "Delivery"): 123.45},
                       {"fonte": "t", "medido_em": "m"})
        a = p["apresentacao"]
        self.assertEqual((a["chave"], a["linha_de_corte"], a["base"]), ("subcategoria", "2025-12-22",
                         {"inicio": "2025-01", "fim": "2025-11", "meses": 11}))
        self.assertTrue(a["rodape"].startswith("Com base nos seus registros até 22/12/2025 (média de jan/2025 a nov/2025"))
        self.assertNotIn("proje", a["rodape"].lower())
        self.assertEqual(p["compromissos"][0]["ate_linha_de_corte"], 123.45)
        self.assertIn("(jan/2025 a nov/2025) · Nível 1 (supérfluo)", p["compromissos"][0]["raciocinio"])

    # --- provas negativas ---
    def test_sem_medicao_de_dezembro_diz_nao_medido(self):
        p = apresentar(montar_proposta({"inflow_mensal": 10000.0, "surplus_mensal": 1000.0}, LINHAS),
                       "2025-12-22", None, None, None)
        self.assertEqual(p["compromissos"][0]["ate_linha_de_corte"], "NAO_MEDIDO")
        self.assertEqual(p["apresentacao"]["base"], "NAO_MEDIDO")

    def test_subcategoria_sem_gasto_em_dezembro_e_zero_medido(self):
        p = apresentar(montar_proposta({"inflow_mensal": 10000.0, "surplus_mensal": 1000.0}, LINHAS),
                       "2025-12-22", None, {}, None)
        self.assertEqual(p["compromissos"][0]["ate_linha_de_corte"], 0.0)

    def test_rota_exige_ref(self):
        r = Client().post("/api/v1/context-agent/i-agora/plano/proposta/", {}, content_type="application/json")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
