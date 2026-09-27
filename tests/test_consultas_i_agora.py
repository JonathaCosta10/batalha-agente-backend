"""Consultas do estudo i.agora (apps/context_agent_datadriven/pastas_raiz/estudos/i_agora/consultas.py).

Cada regra tem a sua prova negativa: um caso ruim que TEM de reprovar.
Não liga o Django nem toca no BigQuery: as bases são montadas aqui, à mão.
"""

import unittest

import pandas as pd

from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora import consultas as c


def _linha(cliente, mes, tipo, macro, valor):
    return {"id_usuario": cliente, "mes": mes, "tipo": tipo, "macro": macro,
            "valor": valor, "valor_direcional": valor if tipo == "E" else -valor}


def _base_notebook():
    """Dois clientes em dezembro: A fecha negativo (-100), B positivo."""
    linhas = []
    for cliente, renda, fator in (("A", 1000.0, 1.1), ("B", 1000.0, 0.5)):
        linhas.append(_linha(cliente, 12, "E", c.MACRO_RENDA, renda))
        for macro, peso in ((c.MACRO_ESSENCIAL, 0.4), (c.MACRO_FLEXIVEL, 0.3),
                            (c.MACRO_SUPERFLUO, 0.2), (c.MACRO_BANCO, 0.1)):
            linhas.append(_linha(cliente, 12, "S", macro, renda * fator * peso))
    return pd.DataFrame(linhas)


class RegrasDeClassificacao(unittest.TestCase):
    def test_tres_grupos_nos_limiares(self):
        self.assertEqual(c.classificar_saude(-0.01, 50), c.CLUSTER_ENDIVIDADO)
        self.assertEqual(c.classificar_saude(10, 14.99), c.CLUSTER_VULNERAVEL)
        self.assertEqual(c.classificar_saude(10, 15), c.CLUSTER_SAUDAVEL)

    def test_faixas_salariais_incluem_o_limite_superior(self):
        self.assertEqual(c.classificar_faixa_salarial(2500), "Até R$ 2.500")
        self.assertEqual(c.classificar_faixa_salarial(5000.01), "R$ 5.001 a R$ 10.000")
        self.assertEqual(c.classificar_faixa_salarial(10000.01), "Acima de R$ 10.000")

    def test_diagnostico_50_30_20_respeita_a_ordem_das_regras(self):
        # CLT_0007 da célula 19: fixo 59,7% ganha de variável 41,1% e investimento -0,9%.
        self.assertEqual(c.diagnostico_50_30_20(59.7, 41.1, -0.9), "Alerta Fixo")
        self.assertEqual(c.diagnostico_50_30_20(40, 24, 35), "Perfil Equilibrado")

    def test_margem_e_essencialidade(self):
        self.assertEqual(c.classificar_essencialidade("Casa"), c.NIVEL_3)
        self.assertEqual(c.classificar_essencialidade("Restaurantes"), c.NIVEL_2)
        self.assertEqual(c.classificar_essencialidade("Lazer"), c.NIVEL_1)
        self.assertEqual(c.margem_de_corte_seguro(100, 50), 125)

    def test_negativa_produto_para_cluster_desconhecido_reprova(self):
        with self.assertRaises(ValueError):
            c.recomendar_produto("4. Investidor")

    def test_negativa_meta_com_zero_meses_reprova(self):
        with self.assertRaises(ValueError):
            c.meta_de_economia_mensal(600, meses=0)


class CoorteEFlexibilidade(unittest.TestCase):
    def test_coorte_de_dezembro_e_score(self):
        df = _base_notebook()
        mensal = c.agregar_mensal(df)
        coorte = c.coorte_negativada(mensal)
        self.assertEqual(list(coorte["id_usuario"]), ["A"])
        self.assertAlmostEqual(float(coorte["divida_atual"].iloc[0]), 100.0)
        tabela = c.score_de_flexibilidade(df, coorte)
        self.assertAlmostEqual(float(tabela["score_de_flexibilidade_pct"].iloc[0]), 50.0)
        self.assertAlmostEqual(float(tabela["meta_de_economia_mensal"].iloc[0]), 100.0 / 6)

    def test_negativa_nomes_da_celula_36_reprovam(self):
        # A célula 36 procurava 'Flexivel' e 'Banco'; a base tinha 'Flexivel/Delivery' e 'Banco/Taxas'.
        # Lá virava coluna zerada e score 20% para todos; aqui TEM de reprovar.
        df = _base_notebook().replace({"macro": {c.MACRO_FLEXIVEL: "Flexivel", c.MACRO_BANCO: "Banco"}})
        coorte = c.coorte_negativada(c.agregar_mensal(df))
        with self.assertRaises(ValueError):
            c.score_de_flexibilidade(df, coorte)


class ExtratoReal(unittest.TestCase):
    def test_normaliza_colunas_do_bigquery(self):
        extrato = pd.DataFrame({
            "id_usuario": ["u1", "u1"], "anomes": [202512, 202512], "tipo": ["E", "S"],
            "vlr": [3000.0, 120.5], "nom_cate_macro": ["Salarios e bonificacoes", "Mercado"],
            "nom_cate_micro": ["Salario CLT", "Mercado"],
        })
        df = c.normalizar_extrato(extrato)
        self.assertEqual(list(df["valor_direcional"]), [3000.0, -120.5])
        self.assertEqual(float(c.agregar_mensal(df)["saldo"].iloc[0]), 2879.5)

    def test_negativa_score_recusa_taxonomia_real(self):
        # A base real não tem as macros do notebook: o score não pode sair com categorias zeradas.
        extrato = pd.DataFrame({
            "id_usuario": ["u1", "u1"], "anomes": [202512, 202512], "tipo": ["E", "S"],
            "vlr": [100.0, 300.0], "nom_cate_macro": ["Salarios e bonificacoes", "Mercado"],
            "nom_cate_micro": ["Salario CLT", "Mercado"],
        })
        df = c.normalizar_extrato(extrato)
        with self.assertRaises(ValueError):
            c.score_de_flexibilidade(df, c.coorte_negativada(c.agregar_mensal(df)))

    def test_negativa_tipo_fora_de_e_s_reprova(self):
        extrato = pd.DataFrame({"id_usuario": ["u1"], "anomes": [202501], "tipo": ["X"], "vlr": [1.0],
                                "nom_cate_macro": ["Mercado"], "nom_cate_micro": ["Mercado"]})
        with self.assertRaises(ValueError):
            c.normalizar_extrato(extrato)


if __name__ == "__main__":
    unittest.main()
