"""Especificação §4: Flexibility e Behavior de 0 a 100.

Flexibility = 40 % margem + 30 % comprometimento com fixos e parcelas + 30 % estabilidade.
Behavior    = 100 − penalidades (margem 40 %, crédito/cheque especial 35 %, volatilidade 25 %).
Normalização de cada componente: DECIDIDO 2026-09-27 (dono aceitou a recomendação) (D-12) em services/metricas_fluxo.py (margem linear até 100 %).
Fato que motivou o teste de não saturação: score com corte em 15 % deu média EXATAMENTE 100,0 no Esbanjador e no
Livre (q_spec_diagnostico.json · 2026-09-27T09:17 BRT).
Prova negativa: pesos somando 95 reprovam; um score saturado não separa margem 20 % de 60 %.
"""

import unittest
from decimal import Decimal

from apps.context_agent_datadriven.services import metricas_fluxo as mf


def mes(anomes, inflow, outflow, **kw):
    return {"anomes": anomes, "inflow": inflow, "outflow": outflow, **kw}


def serie(inflow, outflow, n=12, **kw):
    return [mes(202500 + m, inflow, outflow, **kw) for m in range(1, n + 1)]


def pesos_somam_100(pesos):
    return sum(Decimal(v) for v in pesos.values()) == 100


def score_saturado(margem_pct):
    """O score hipotético da medição da base: clip(100 * margem / 15, 0, 100)."""
    return max(Decimal(0), min(Decimal(100), Decimal(100) * Decimal(margem_pct) / 15))


class Pesos(unittest.TestCase):
    def test_pesos_somam_100(self):
        self.assertTrue(pesos_somam_100(mf.PESOS_FLEXIBILITY))
        self.assertTrue(pesos_somam_100(mf.PESOS_BEHAVIOR))

    def test_pesos_da_especificacao(self):
        self.assertEqual({k: int(v) for k, v in mf.PESOS_FLEXIBILITY.items()},
                         {"margem": 40, "comprometimento": 30, "estabilidade": 30})
        self.assertEqual({k: int(v) for k, v in mf.PESOS_BEHAVIOR.items()},
                         {"margem": 40, "credito": 35, "volatilidade": 25})


class Flexibility(unittest.TestCase):
    def test_valor_conhecido(self):
        # margem 20 % -> 0,20·40 = 8; comprometimento 1 − 500/1000 -> 0,5·30 = 15; estabilidade 3/3 -> 30.
        r = mf.flexibility_score(serie(1000, 800, n=3, fixo=300, parcelas=200))
        self.assertEqual(r["score"], Decimal(53))

    def test_estabilidade_conta_meses_com_superavit(self):
        meses = serie(1000, 900, n=4)
        meses[0]["outflow"] = 1100
        self.assertEqual(mf.flexibility_score(meses)["componentes"]["estabilidade"], Decimal("0.75"))

    def test_inflow_zero_nao_medido(self):
        r = mf.flexibility_score(serie(0, 500))
        self.assertEqual((r["score"], r["estado"]), (None, mf.NAO_MEDIDO))
        self.assertIsNone(mf.flexibility_score([])["score"])

    def test_monotonia_mais_margem_nunca_baixa(self):
        anterior = None
        for outflow in range(1500, -1, -50):
            s = mf.flexibility_score(serie(1000, outflow, fixo=min(200, outflow)))["score"]
            if anterior is not None:
                self.assertGreaterEqual(s, anterior, f"outflow={outflow}")
            anterior = s


class Behavior(unittest.TestCase):
    def test_valor_conhecido(self):
        # margem 10 % -> penalidade 0,9·40 = 36; crédito 1/4 -> 8,75; volatilidade 0.
        meses = serie(1000, 900, n=4)
        meses[2]["uso_cheque_especial"] = True
        self.assertEqual(mf.behavior_score(meses)["score"], Decimal("55.25"))

    def test_volatilidade_penaliza(self):
        estavel = mf.behavior_score(serie(1000, 800, n=4))["score"]
        volatil = mf.behavior_score([mes(202501, 200, 160), mes(202502, 1800, 1440),
                                     mes(202503, 200, 160), mes(202504, 1800, 1440)])["score"]
        self.assertLess(volatil, estavel)

    def test_menos_de_2_meses_volatilidade_nao_medida(self):
        r = mf.behavior_score(serie(1000, 800, n=1))
        self.assertIn("volatilidade_nao_medida_menos_de_2_meses", r["pendencias"])

    def test_inflow_zero_nao_medido(self):
        self.assertIsNone(mf.behavior_score(serie(0, 100))["score"])

    def test_monotonia_margem_e_credito(self):
        anterior = None
        for outflow in range(1500, -1, -50):
            s = mf.behavior_score(serie(1000, outflow))["score"]
            if anterior is not None:
                self.assertGreaterEqual(s, anterior)
            anterior = s
        sem = mf.behavior_score(serie(1000, 800))["score"]
        com = mf.behavior_score(serie(1000, 800, credito_emergencial=10))["score"]
        self.assertLess(com, sem)


class Faixa(unittest.TestCase):
    def test_scores_sempre_em_0_100(self):
        for inflow in (1, 1000, 50000):
            for fator in ("0", "0.5", "0.85", "1", "3", "40"):
                for credito in (0, 1):
                    outflow = Decimal(inflow) * Decimal(fator)
                    meses = serie(inflow, outflow, fixo=outflow, parcelas=outflow, credito_emergencial=credito)
                    meses[0]["inflow"] = inflow * 7  # volatilidade alta
                    for f in (mf.flexibility_score, mf.behavior_score):
                        s = f(meses)["score"]
                        self.assertTrue(0 <= s <= 100, f"{f.__name__} {inflow} {fator} {credito}: {s}")
                    s = mf.behavior_score(meses, zerar_credito=True)["score"]
                    self.assertTrue(0 <= s <= 100)


class NaoSatura(unittest.TestCase):
    def test_margem_20_e_60_dao_scores_diferentes(self):
        c20, c60 = serie(1000, 800), serie(1000, 400)
        f20, f60 = mf.flexibility_score(c20)["score"], mf.flexibility_score(c60)["score"]
        b20, b60 = mf.behavior_score(c20)["score"], mf.behavior_score(c60)["score"]
        self.assertGreater(f60, f20)
        self.assertGreater(b60, b20)
        self.assertLess(f60, 100)

    # --- prova negativa
    def test_score_saturado_nao_separa_20_de_60(self):
        self.assertEqual(score_saturado(20), score_saturado(60))

    def test_pesos_errados_reprovam(self):
        self.assertFalse(pesos_somam_100({"margem": 40, "credito": 30, "volatilidade": 25}))


class DivergenciaComCodigoAtual(unittest.TestCase):
    @unittest.expectedFailure
    def test_score_maximo_da_especificacao_nao_e_nivel_baixo(self):
        """DIVERGE. O único score comportamental do código, apps/recomendacao/services/behavioral_score.py:17-29,
        LÊ `score_comportamental` pronto numa escala 0–1000 (cortes 750 e 450) e não calcula Flexibility nem
        Behavior. Um Behavior 100 (o melhor da especificação) cai em nivel BAIXO."""
        from apps.recomendacao.services.behavioral_score import BehavioralScoreEngine
        melhor = mf.behavior_score(serie(1000, 0))["score"]
        self.assertEqual(melhor, 100)
        cliente = {"score_comportamental": int(melhor), "genero": "F", "nome": "Teste", "id": "x",
                   "diretriz_comportamental": "-"}
        self.assertNotEqual(BehavioralScoreEngine.calcular_indice_contexto(cliente)["nivel"], "BAIXO")


if __name__ == "__main__":
    unittest.main()
