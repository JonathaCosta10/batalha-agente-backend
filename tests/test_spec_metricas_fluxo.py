"""Especificação §1: métricas por cliente × mês (Inflow, Outflow, Surplus, Margem, Fixo × Variável).

Módulo sob teste: apps/context_agent_datadriven/services/metricas_fluxo.py (puro, sem Django).
Prova negativa: tipo de lançamento desconhecido e valor ausente TÊM de reprovar; margem calculada sobre o
Outflow (erro comum) tem de dar outro número.
"""

import json
import unittest
from decimal import Decimal
from pathlib import Path

from apps.context_agent_datadriven.services import metricas_fluxo as mf

RAIZ = Path(__file__).resolve().parents[1]
Q02 = RAIZ / "docs" / "estudo-i-agora" / "medicoes" / "2026-09-27" / "q02_categorias.json"
U1, U2 = "u-1", "u-2"


def L(anomes, tipo, valor, macro="", micro="", usuario=U1, saldo_apos=None):
    return mf.Lancamento(usuario, anomes, tipo, valor, macro, micro, saldo_apos)


class Fluxos(unittest.TestCase):
    def test_inflow_outflow_surplus_margem(self):
        m = mf.metricas_mes([L(202501, "V", 1000), L(202501, "F", 600), L(202501, "F", 250)])[(U1, 202501)]
        self.assertEqual((m.inflow, m.outflow, m.surplus), (Decimal(1000), Decimal(850), Decimal(150)))
        self.assertEqual(m.margem_pct, Decimal(15))

    def test_tipos_v_true_e_da_base_equivalem(self):
        # A especificação fala em V/True; a base usa E/S (q_spec_diagnostico.json, 2026-09-27T09:17 BRT).
        a = mf.metricas_mes([L(202501, "V", 100), L(202501, "F", 40)])[(U1, 202501)]
        b = mf.metricas_mes([L(202501, True, 100), L(202501, False, 40)])[(U1, 202501)]
        c = mf.metricas_mes([L(202501, "E", 100), L(202501, "S", 40)])[(U1, 202501)]
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_valor_em_modulo(self):
        m = mf.metricas_mes([L(202501, "E", "1000.00"), L(202501, "S", "-400.00")])[(U1, 202501)]
        self.assertEqual(m.outflow, Decimal("400.00"))

    def test_chave_cliente_mes(self):
        r = mf.metricas_mes([L(202501, "E", 10), L(202502, "E", 20), L(202501, "E", 30, usuario=U2)])
        self.assertEqual(sorted(r), [(U1, 202501), (U1, 202502), (U2, 202501)])

    def test_fronteira_margem_exatamente_15(self):
        self.assertEqual(mf.margem_pct(1000, 850), Decimal(15))
        self.assertLess(mf.margem_pct(1000, "850.01"), mf.LIMIAR_MARGEM_PCT)

    def test_float_nao_herda_erro_binario(self):
        # 1 - 0.85 em float = 0.15000000000000002; via Decimal(str()) fica 15 exato.
        self.assertEqual(mf.margem_pct(1.0, 0.85), Decimal(15))

    def test_inflow_zero_margem_nao_medida(self):
        m = mf.metricas_mes([L(202501, "S", 300)])[(U1, 202501)]
        self.assertEqual(m.inflow, 0)
        self.assertIsNone(m.margem_pct)          # nunca 0 nem -100 %
        self.assertEqual(m.surplus, Decimal(-300))


class FixoVariavel(unittest.TestCase):
    def test_fixo_moradia_luz_agua(self):
        ls = [L(202501, "S", 1500, "Casa", "Pagamento de aluguel"), L(202501, "S", 200, "Casa", "Energia eletrica"),
              L(202501, "S", 90, "Casa", "Agua e esgoto"), L(202501, "S", 80, "Casa", "Gas")]
        m = mf.metricas_mes(ls)[(U1, 202501)]
        self.assertEqual(m.fixo, Decimal(1790))   # gás fora: a especificação não cita

    def test_variavel_lazer_compras_restaurantes(self):
        ls = [L(202501, "S", 100, "Lazer", "Cinema"), L(202501, "S", 200, "Lojas e sites", "Compras"),
              L(202501, "S", 50, "Restaurantes", "Padaria"), L(202501, "S", 70, "Delivery", "Delivery")]
        m = mf.metricas_mes(ls)[(U1, 202501)]
        self.assertEqual(m.variavel, Decimal(350))  # delivery fora: a especificação não cita

    def test_mapas_existem_na_taxonomia_medida(self):
        """Toda categoria dos mapas existe em q02 (2026-09-27T03:48 BRT): nome errado reprova."""
        linhas = json.loads(Q02.read_text(encoding="utf-8"))["linhas"]
        pares = {(l["nom_cate_macro"], l["nom_cate_micro"]) for l in linhas if l["tipo"] == "S"}
        macros = {m for m, _ in pares}
        for par in (mf.FIXO_SUBCATEGORIAS | mf.PARCELAS_SUBCATEGORIAS | mf.TARIFAS_SUBCATEGORIAS
                    | mf.MULTA_SUBCATEGORIAS | {mf.FINANCIAMENTO_IMOVEL}):
            self.assertIn(par, pares)
        self.assertLessEqual(mf.VARIAVEL_MACROS, macros)


class ProvaNegativa(unittest.TestCase):
    def test_tipo_desconhecido_reprova(self):
        for tipo in ("X", None, 1, "entrada?"):
            with self.assertRaises(ValueError):
                mf.metricas_mes([L(202501, tipo, 10)])

    def test_valor_ausente_nao_vira_zero(self):
        with self.assertRaises(ValueError):
            mf.metricas_mes([L(202501, "E", None)])

    def test_margem_sobre_outflow_da_outro_numero(self):
        errada = lambda i, o: (Decimal(i) - Decimal(o)) / Decimal(o) * 100  # noqa: E731
        self.assertNotEqual(errada(1000, 850), mf.margem_pct(1000, 850))

    def test_categoria_inexistente_reprova_o_teste_de_taxonomia(self):
        linhas = json.loads(Q02.read_text(encoding="utf-8"))["linhas"]
        pares = {(l["nom_cate_macro"], l["nom_cate_micro"]) for l in linhas}
        self.assertNotIn(("Casa", "Luz"), pares)  # "luz" da especificação é "Energia eletrica" na base


if __name__ == "__main__":
    unittest.main()
