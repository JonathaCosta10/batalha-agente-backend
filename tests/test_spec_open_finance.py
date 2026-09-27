"""Especificação §6 (Open Finance, futuro).

- Surplus < 0 com patrimônio investido > R$ 50.000 => "Esbanjador de Risco Controlado";
- atraso > 15 dias em fatura externa => zera o componente de crédito do Behavior (DECIDIDO 2026-09-27 (dono aceitou a recomendação), D-16;
  ZERAR_CREDITO_E_PENALIDADE_MAXIMA: penalidade de crédito máxima, 35 pontos).
Prova negativa: dado ausente (None) não dispara nada e é declarado como não medido.
"""

import json
import unittest
from decimal import Decimal
from pathlib import Path

from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora import t3
from apps.context_agent_datadriven.services import metricas_fluxo as mf

RAIZ = Path(__file__).resolve().parents[1]
FLUXOS = RAIZ / "apps" / "conversas" / "fluxos_comportamento.json"
OF = mf.DadosOpenFinance


def serie(inflow, outflow, n=6):
    return [{"anomes": 202500 + m, "inflow": inflow, "outflow": outflow} for m in range(1, n + 1)]


class Patrimonio(unittest.TestCase):
    def test_fronteira_50000(self):
        self.assertEqual(mf.ajustar_open_finance(mf.VULNERAVEL, -1, OF(50000))["segmento"], mf.VULNERAVEL)
        self.assertEqual(mf.ajustar_open_finance(mf.VULNERAVEL, -1, OF("50000.01"))["segmento"],
                         mf.ESBANJADOR_RISCO_CONTROLADO)

    def test_exige_surplus_negativo(self):
        self.assertEqual(mf.ajustar_open_finance(mf.LIVRE, 0, OF(900000))["segmento"], mf.LIVRE)
        self.assertEqual(mf.ajustar_open_finance(mf.LIVRE, 10, OF(900000))["segmento"], mf.LIVRE)

    def test_aceita_dict(self):
        r = mf.ajustar_open_finance(mf.VULNERAVEL, -5, {"patrimonio_investido": 60000})
        self.assertEqual(r["segmento"], mf.ESBANJADOR_RISCO_CONTROLADO)


class Atraso(unittest.TestCase):
    def test_fronteira_15_contra_16_dias(self):
        self.assertFalse(mf.ajustar_open_finance(mf.LIVRE, 1, OF(None, 15))["zerar_componente_credito"])
        self.assertTrue(mf.ajustar_open_finance(mf.LIVRE, 1, OF(None, 16))["zerar_componente_credito"])

    def test_zerar_leva_penalidade_de_credito_ao_maximo(self):
        normal = mf.behavior_score(serie(1000, 800))
        zerado = mf.behavior_score(serie(1000, 800), zerar_credito=True)
        self.assertEqual(zerado["penalidades"]["credito"], 1)
        self.assertEqual(normal["score"] - zerado["score"], mf.PESOS_BEHAVIOR["credito"])

    def test_fluxo_completo(self):
        aj = mf.ajustar_open_finance(mf.LIVRE, 200, OF(0, 30))
        s = mf.behavior_score(serie(1000, 800), zerar_credito=aj["zerar_componente_credito"])["score"]
        self.assertEqual(s, Decimal(100) - Decimal("0.8") * 40 - 35)


class ProvaNegativa(unittest.TestCase):
    def test_ausente_nao_dispara_e_e_declarado(self):
        r = mf.ajustar_open_finance(mf.VULNERAVEL, -1000, OF())
        self.assertEqual(r["segmento"], mf.VULNERAVEL)
        self.assertFalse(r["zerar_componente_credito"])
        self.assertEqual(r["nao_medidos"], ["patrimonio_investido", "atraso_fatura_externa_dias"])

    def test_surplus_ausente_nao_vira_zero_nem_negativo(self):
        self.assertEqual(mf.ajustar_open_finance(mf.LIVRE, None, OF(10**6))["segmento"], mf.LIVRE)


class DivergenciaComCodigoAtual(unittest.TestCase):
    @unittest.expectedFailure
    def test_t3_atual_conhece_o_segmento_open_finance(self):
        """NÃO EXISTE. t3.py:29 declara só SEGMENTOS = (Vulnerável, Esbanjador, Livre)."""
        self.assertIn(mf.ESBANJADOR_RISCO_CONTROLADO, t3.SEGMENTOS)

    @unittest.expectedFailure
    def test_fluxos_tem_tom_para_o_segmento_open_finance(self):
        """NÃO EXISTE. apps/conversas/fluxos_comportamento.json:11-228 tem fluxos para Vulnerável, Esbanjador,
        Livre e NAO_MEDIDO; o novo segmento cairia sem fluxo."""
        fluxos = json.loads(FLUXOS.read_text(encoding="utf-8"))["fluxos"]
        self.assertIn(mf.ESBANJADOR_RISCO_CONTROLADO, fluxos)


if __name__ == "__main__":
    unittest.main()
