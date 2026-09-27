"""Especificação §2: má × boa dívida e avaliação longitudinal jan–dez.

Fatos da base usados (selo): a base NÃO tem categoria de cheque especial nem de juros rotativos
(q02_categorias.json · 2026-09-27T03:48 BRT; q_spec_diagnostico.json · 2026-09-27T09:17 BRT).
Prova negativa: "Cheque" (pagamento em cheque) não pode virar cheque especial; 3 déficits com dezembro não podem
ser "sazonais"; financiamento acima de 30 % do Inflow não pode ser "boa dívida".
Divergências com o código atual: @unittest.expectedFailure, com arquivo:linha no comentário.
"""

import json
import unittest
from pathlib import Path

from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora import t3
from apps.context_agent_datadriven.services import metricas_fluxo as mf

RAIZ = Path(__file__).resolve().parents[1]
MEDICOES = RAIZ / "docs" / "estudo-i-agora" / "medicoes" / "2026-09-27"
SQL_POPULACAO = (RAIZ / "apps" / "context_agent_datadriven" / "pastas_raiz" / "estudos" / "i_agora" / "sql"
                 / "populacao_t3.sql")


def ano(deficits=(), a=2025):
    """12 meses; os meses em `deficits` têm Surplus -100, os outros +100."""
    return {a * 100 + m: (-100 if m in deficits else 100) for m in range(1, 13)}


class MaBoaDivida(unittest.TestCase):
    def test_ma_divida_rotulos_da_especificacao(self):
        self.assertEqual(mf.classificar_divida("Open Finance", "Cheque especial")["subtipo"], "cheque_especial")
        self.assertEqual(mf.classificar_divida("Open Finance", "Juros rotativos do cartao")["subtipo"], "juros_rotativos")
        for micro in ("Outras tarifas financeiras", "Anuidade e pacote de servico"):
            r = mf.classificar_divida("Produtos financeiros", micro)
            self.assertEqual((r["classe"], r["subtipo"], r["credito_emergencial"]), (mf.MA_DIVIDA, "tarifas", False))

    def test_cheque_especial_e_rotativo_sao_credito_emergencial(self):
        self.assertTrue(mf.classificar_divida("x", "Cheque especial")["credito_emergencial"])
        self.assertTrue(mf.classificar_divida("x", "Juros rotativos")["credito_emergencial"])

    def test_juros_pagos_e_ma_divida_mas_nao_gatilho(self):
        r = mf.classificar_divida("Produtos financeiros", "Juros pagos")
        self.assertEqual((r["classe"], r["credito_emergencial"]), (mf.MA_DIVIDA, False))

    def test_financiamento_compativel_fronteira_30pct(self):
        f = mf.FINANCIAMENTO_IMOVEL
        self.assertEqual(mf.classificar_divida(*f, valor_mensal=3000, inflow_mensal=10000)["classe"], mf.BOA_DIVIDA)
        self.assertEqual(mf.classificar_divida(*f, valor_mensal="3000.01", inflow_mensal=10000)["classe"],
                         mf.FINANCIAMENTO_INCOMPATIVEL)

    def test_financiamento_sem_inflow_nao_medido(self):
        f = mf.FINANCIAMENTO_IMOVEL
        self.assertEqual(mf.classificar_divida(*f, valor_mensal=1000)["classe"], mf.NAO_MEDIDO)
        self.assertEqual(mf.classificar_divida(*f, valor_mensal=1000, inflow_mensal=0)["classe"],
                         mf.FINANCIAMENTO_INCOMPATIVEL)

    def test_base_nao_tem_cheque_especial_nem_rotativo(self):
        """Fato medido que obriga ao proxy (DECIDIDO 2026-09-27 (dono aceitou a recomendação): CHEQUE_ESPECIAL_PROXY_*, D-10)."""
        linhas = json.loads((MEDICOES / "q02_categorias.json").read_text(encoding="utf-8"))["linhas"]
        micros = {mf.normalizar(l["nom_cate_micro"]) for l in linhas}
        self.assertFalse([m for m in micros if "cheque especial" in m or "rotativo" in m])
        self.assertIn("cheque", micros)

    def test_proxy_saldo_negativo_marca_uso_de_cheque_especial(self):
        ls = [mf.Lancamento("u", 202501, "E", 100, saldo_apos=50), mf.Lancamento("u", 202501, "S", 200, saldo_apos=-50)]
        self.assertTrue(mf.metricas_mes(ls)[("u", 202501)].uso_cheque_especial)
        ls = [mf.Lancamento("u", 202501, "S", 200, saldo_apos=None)]
        self.assertFalse(mf.metricas_mes(ls)[("u", 202501)].uso_cheque_especial)  # ausente não é negativo

    # --- prova negativa
    def test_pagamento_em_cheque_nao_e_cheque_especial(self):
        r = mf.classificar_divida("Outros gastos", "Cheque")
        self.assertEqual(r["classe"], mf.FORA_DA_SPEC)
        self.assertFalse(r["credito_emergencial"])

    def test_financiamento_caro_nunca_e_boa_divida(self):
        r = mf.classificar_divida(*mf.FINANCIAMENTO_IMOVEL, valor_mensal=6000, inflow_mensal=10000)
        self.assertNotEqual(r["classe"], mf.BOA_DIVIDA)


class Longitudinal(unittest.TestCase):
    def test_deficit_so_em_dezembro_e_sazonal(self):
        r = mf.avaliar_longitudinal(ano({12}))
        self.assertEqual((r["classe"], r["meses_deficit"], r["completo"]), (mf.SAZONAL, [202512], True))

    def test_dois_meses_nao_e_insustentavel(self):
        self.assertEqual(mf.avaliar_longitudinal(ano({3, 12}))["classe"], mf.PONTUAL)
        self.assertEqual(mf.avaliar_longitudinal(ano({3, 7}))["classe"], mf.PONTUAL)

    def test_tres_meses_e_insustentavel(self):
        self.assertEqual(mf.avaliar_longitudinal(ano({3, 7, 9}))["classe"], mf.INSUSTENTAVEL)

    def test_sem_deficit_e_surplus_zero_nao_e_deficit(self):
        serie = ano()
        serie[202512] = 0
        self.assertEqual(mf.avaliar_longitudinal(serie)["classe"], mf.SEM_DEFICIT)

    def test_janela_incompleta_e_vazia(self):
        r = mf.avaliar_longitudinal({202512: -10})
        self.assertEqual((r["classe"], r["completo"]), (mf.SAZONAL, False))
        self.assertEqual(mf.avaliar_longitudinal({})["classe"], mf.NAO_MEDIDO)

    def test_aceita_metricas_mes(self):
        ls = [mf.Lancamento("u", 202512, "E", 100), mf.Lancamento("u", 202512, "S", 150)]
        self.assertEqual(mf.avaliar_longitudinal(mf.metricas_mes(ls).values())["classe"], mf.SAZONAL)

    # --- prova negativa
    def test_tres_deficits_com_dezembro_nao_sao_sazonais(self):
        self.assertNotEqual(mf.avaliar_longitudinal(ano({10, 11, 12}))["classe"], mf.SAZONAL)


class DivergenciaComCodigoAtual(unittest.TestCase):
    @unittest.expectedFailure
    def test_financiamento_compativel_nao_e_divida_relevante(self):
        """DIVERGE. apps/conversas/interacao_dados.py:94 soma a macro inteira "Emprestimos e financiamentos"
        (inclui Financiamento de imovel) em `emprestimos`, e interacao_dados.py:267-273 decide `relevante` sobre
        esse total (regra divida.relevante, >= 10 %). Pela especificação, financiamento imobiliário compatível
        (20 % do Inflow) é BOA dívida: o cliente não tem dívida cara."""
        from apps.conversas import interacao_dados as dd
        linhas = [{"emprestimos": 2000, "juros_pagos": 0, "multas_atraso": 0}] * 3
        self.assertFalse(dd.resumir_divida(linhas, 10000)["relevante"])

    @unittest.expectedFailure
    def test_t3_atual_separa_boa_de_ma_divida(self):
        """DIVERGE. t3.py:46-47 põe "Emprestimos e financiamentos" (financiamento imobiliário = boa dívida) e
        "Produtos financeiros" (juros e tarifas = má dívida) no MESMO grupo compromisso_financeiro."""
        self.assertNotEqual(t3.MAPA_GRUPOS["Emprestimos e financiamentos"], t3.MAPA_GRUPOS["Produtos financeiros"])

    @unittest.expectedFailure
    def test_janela_do_t3_inclui_dezembro(self):
        """DIVERGE. A especificação avalia jan–dez (déficit só em dezembro = sazonal). O T3 atual corta a janela
        antes do mês do corte: populacao_t3.sql:9 (`e.anomes < ... @data_corte`) e t3.py:8-9 (jan–nov/2025).
        Dezembro nunca entra, então o caso sazonal não é visível."""
        self.assertNotIn("e.anomes < CAST(FORMAT_DATE('%Y%m', @data_corte) AS INT64)",
                         SQL_POPULACAO.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
