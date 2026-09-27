"""Segmentação T3, visões por assunto, guard de inclusão do dado e estatística (estudos/i_agora).

Cada regra tem a sua prova negativa: um caso ruim que TEM de reprovar.
Não toca no BigQuery: o executor falso devolve a linha que a visão devolveria.
A prova no BigQuery real é docs/estudo-i-agora/sql/medir_t3.py (medicoes/<data>/guard_e2e.json).
"""

import json
import unittest
from pathlib import Path

from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora import estatistica, guard, t3, visoes

RAIZ = Path(__file__).resolve().parents[1]
Q06 = RAIZ / "docs" / "estudo-i-agora" / "medicoes" / "2026-09-27" / "q06_composicao_saidas.json"

LINHAS = {
    "perfil_t3": {"meses": 11, "inflow_mensal": 7927.49, "outflow_mensal": 9345.10, "surplus_mensal": -1417.61,
                  "taxa_surplus_pct": -17.88, "essencial_mensal": 2900.0, "compromisso_mensal": 4141.27,
                  "discricionario_mensal": 1500.0, "nao_classificado_mensal": 803.83, "saidas_sem_grupo": 0,
                  "segmento_t3": t3.VULNERAVEL},
    "dividas": {"compromisso_total": 45553.97, "compromisso_mensal": 4141.27, "fatura_total": 12000.0,
                "emprestimos_financiamentos_total": 20000.0, "juros_pagos_total": 350.5, "multas": 2,
                "lancamentos_parcelados": 30, "pct_inflow_comprometido": 52.24},
    "categoria": {"categoria": "Delivery", "grupo": "discricionario", "lancamentos": 40, "total": 2200.0,
                  "media_mensal": 200.0, "pct_do_outflow": 2.14, "meses": 11},
}
TEXTO_OK = ("Sei que o mês está em aperto. Vamos organizar juntos, passo a passo: o compromisso financeiro "
            "soma R$ 4.141,27 por mês, 52,24% do que entra. O primeiro passo é renegociar com segurança.")


class ExecutorFalso:
    """Reconhece a visão pela 1ª linha (comentário) do arquivo SQL e devolve a linha fixa."""

    def __init__(self, linhas=LINHAS):
        self.linhas, self.chamadas = linhas, []

    def executar(self, sql, parametros):
        topico = next(t for t, cfg in visoes.TOPICOS.items()
                      if (visoes.PASTA_SQL / cfg["arquivo"]).read_text(encoding="utf-8").splitlines()[0] in sql)
        self.chamadas.append((topico, parametros))
        return [dict(self.linhas[topico])]


def _envio(**mudar):
    base = {"id_usuario": "cliente-x", "data_corte": "2025-12-22", "topico": "dividas",
            "segmento_t3": t3.VULNERAVEL, "texto": TEXTO_OK,
            "dados": {"compromisso_mensal": 4141.27, "pct_inflow_comprometido": "52,24%"}}
    return {**base, **mudar}


class RegraT3(unittest.TestCase):
    def test_fronteiras(self):
        self.assertEqual(t3.classificar_t3(1000, 850, 0), t3.LIVRE)          # exatamente 15%
        self.assertEqual(t3.classificar_t3(1000, 851, 1), t3.ESBANJADOR)     # 14,9% + 0,1% discricionário
        self.assertEqual(t3.classificar_t3(1000, 1100, 250), t3.ESBANJADOR)  # -10% + 25% = 15%
        self.assertEqual(t3.classificar_t3(1000, 1100, 249), t3.VULNERAVEL)  # -10% + 24,9% < 15%
        self.assertEqual(t3.classificar_t3(0, 500, 500), t3.VULNERAVEL)      # sem inflow não há taxa

    def test_limiar_de_sensibilidade(self):
        self.assertEqual(t3.classificar_t3(1000, 880, 0, limiar=0.10), t3.LIVRE)
        self.assertEqual(t3.classificar_t3(1000, 880, 0), t3.VULNERAVEL)

    def test_mapa_cobre_as_macros_medidas_em_q06(self):
        medidas = [linha["nom_cate_macro"] for linha in json.loads(Q06.read_text(encoding="utf-8"))["linhas"]]
        self.assertEqual(len(medidas), 21)
        self.assertEqual(t3.macros_sem_grupo(medidas), [])

    def test_prova_negativa_macro_nova_reprova(self):
        self.assertEqual(t3.macros_sem_grupo(["Mercado", "Cassino online"]), ["Cassino online"])

    def test_sql_sem_marcador_sobrando(self):
        for topico in visoes.TOPICOS:
            self.assertNotIn("{{", visoes.montar_sql(topico))
        with self.assertRaises(ValueError):
            t3.renderizar_sql("SELECT {{OUTRO}}")
        with self.assertRaises(ValueError):
            t3.cte_grupos({"Bar'; DROP": t3.ESSENCIAL})
        with self.assertRaises(ValueError):
            t3.cte_grupos({"Mercado": "supérfluo"})


class Roteamento(unittest.TestCase):
    def test_categoria_citada_vence(self):
        self.assertEqual(visoes.rotear("Quanto gasto com delivery?"), ("categoria", "Delivery"))
        self.assertEqual(visoes.rotear("E com transporte por app, quanto foi?"), ("categoria", "Transporte por app"))

    def test_palavras_chave(self):
        self.assertEqual(visoes.rotear("Minhas dívidas no cartão estão altas?"), ("dividas", None))
        self.assertEqual(visoes.rotear("Minha renda é instável?"), ("renda", None))
        self.assertEqual(visoes.rotear("Quanto me sobra no mês?"), ("perfil_t3", None))

    def test_prova_negativa_fora_do_catalogo(self):
        with self.assertRaises(visoes.ForaDoCatalogo):
            visoes.rotear("Vai chover amanhã?")
        with self.assertRaises(visoes.ForaDoCatalogo):
            visoes.validar_categoria("Cassino")
        with self.assertRaises(visoes.ForaDoCatalogo):
            visoes.montar_sql("astrologia")
        with self.assertRaises(visoes.ForaDoCatalogo):
            visoes.consultar_visao("renda", "x", categoria="Mercado", executor=ExecutorFalso())

    def test_categoria_normalizada_para_a_grafia_da_base(self):
        visao = visoes.consultar_visao("categoria", "x", categoria="DELIVERY", executor=ExecutorFalso())
        self.assertEqual(visao["parametros"]["categoria"], "Delivery")


class Guard(unittest.TestCase):
    def _verificar(self, envio):
        return guard.verificar_envio(envio, ExecutorFalso())

    def test_envio_correto_aprova(self):
        retorno = self._verificar(_envio())
        self.assertEqual(retorno["veredito"], guard.APROVADO, retorno["checagens"])

    def test_prova_negativa_dado_adulterado(self):
        retorno = self._verificar(_envio(dados={"compromisso_mensal": 4241.27}))
        self.assertEqual(retorno["veredito"], guard.REPROVADO)

    def test_prova_negativa_campo_sem_fonte_e_envio_vazio(self):
        self.assertEqual(self._verificar(_envio(dados={"renda_estimada": 9000}))["veredito"], guard.REPROVADO)
        self.assertEqual(self._verificar(_envio(dados={}))["veredito"], guard.REPROVADO)

    def test_prova_negativa_numero_do_texto_sem_fonte(self):
        texto = TEXTO_OK.replace("R$ 4.141,27", "R$ 4.300,00")
        self.assertEqual(self._verificar(_envio(texto=texto))["veredito"], guard.REPROVADO)

    def test_numero_arredondado_vale_na_precisao_escrita(self):
        self.assertEqual(self._verificar(_envio(texto=TEXTO_OK.replace("R$ 4.141,27", "R$ 4.141")))["veredito"],
                         guard.APROVADO)
        self.assertEqual(self._verificar(_envio(texto=TEXTO_OK.replace("R$ 4.141,27", "R$ 4.150")))["veredito"],
                         guard.REPROVADO)

    def test_prova_negativa_valor_escrito_como_reais_sem_cifrao(self):
        # Antes de 2026-09-27 04:40 "4.300,00 reais" escapava da checagem (lacuna apontada pela revisão Gemini).
        self.assertEqual(self._verificar(_envio(texto=TEXTO_OK.replace("R$ 4.141,27", "4.300,00 reais")))["veredito"],
                         guard.REPROVADO)
        self.assertEqual(self._verificar(_envio(texto=TEXTO_OK.replace("R$ 4.141,27", "4.141,27 reais")))["veredito"],
                         guard.APROVADO)

    def test_escala_mil_vale_na_precisao_escrita(self):
        self.assertEqual(self._verificar(_envio(texto=TEXTO_OK.replace("R$ 4.141,27", "R$ 4,1 mil")))["veredito"],
                         guard.APROVADO)
        self.assertEqual(self._verificar(_envio(texto=TEXTO_OK.replace("R$ 4.141,27", "R$ 4,2 mil")))["veredito"],
                         guard.REPROVADO)

    def test_por_cento_por_extenso_e_lido(self):
        self.assertEqual([(n["tipo"], n["valor"]) for n in guard.numeros_do_texto("12,5 por cento")], [("pct", 12.5)])

    def test_prova_negativa_segmento_declarado_errado(self):
        self.assertEqual(self._verificar(_envio(segmento_t3=t3.LIVRE))["veredito"], guard.REPROVADO)

    def test_prova_negativa_euforia_para_vulneravel(self):
        texto = TEXTO_OK + " Aproveite, é incrível!"
        retorno = self._verificar(_envio(texto=texto))
        reprovadas = {c["nome"] for c in retorno["checagens"] if c["resultado"] == guard.REPROVADO}
        self.assertEqual(retorno["veredito"], guard.REPROVADO)
        self.assertTrue({"tom.exclamacoes", "tom.proibidos"} <= reprovadas)

    def test_sentimento_fora_da_faixa_reprova(self):
        texto = "Vamos organizar: está ótimo, excelente, incrível e perfeito."  # escore 1,0 > 0,5
        checagens = guard.verificar_tom(texto, t3.VULNERAVEL)
        self.assertEqual(next(c for c in checagens if c["nome"] == "sentimento")["resultado"], guard.REPROVADO)

    def test_sem_palavra_do_lexico_diz_que_nao_mediu(self):
        checagens = guard.verificar_tom("Vamos organizar os números.", t3.VULNERAVEL)
        self.assertEqual(next(c for c in checagens if c["nome"] == "sentimento")["resultado"], guard.NAO_MEDIDO)
        self.assertEqual(guard.veredito(checagens), guard.NAO_MEDIDO)

    def test_mapa_incompleto_reprova(self):
        linhas = {**LINHAS, "perfil_t3": {**LINHAS["perfil_t3"], "saidas_sem_grupo": 3}}
        retorno = guard.verificar_envio(_envio(), ExecutorFalso(linhas))
        self.assertEqual(retorno["veredito"], guard.REPROVADO)

    def test_normalizacao(self):
        self.assertEqual(guard.normalizar("R$ 1.638,49"), 1638.49)
        self.assertEqual(guard.normalizar("24,57%"), 24.57)
        self.assertEqual(guard.normalizar(" Vulnerável "), "vulneravel")
        self.assertEqual(guard.normalizar(3), 3.0)


class Estatistica(unittest.TestCase):
    POP = [{"id_usuario": str(i), "meses": 11, "inflow": 1000.0, "outflow": 1000.0 - 20 * i, "essencial": 300.0,
            "compromisso": 300.0, "discricionario": 50.0 * (i % 4), "nao_classificado": 0.0, "cv_inflow": 0.1,
            "saidas_sem_grupo": 0} for i in range(20)]

    def test_participacao_soma_100_e_repete(self):
        a = estatistica.relatorio(self.POP)
        b = estatistica.relatorio(self.POP)
        self.assertAlmostEqual(sum(p["pct"] for p in a["participacao"].values()), 100.0)
        self.assertEqual(a["participacao"], b["participacao"])
        self.assertEqual(a["sensibilidade_do_limiar"]["0.15"]["mudaram_vs_015"], 0)

    def test_spearman_monotono_e_prova_negativa_n_pequeno(self):
        r = estatistica.spearman_permutacao(range(30), [x ** 3 for x in range(30)], permutacoes=500)
        self.assertAlmostEqual(r["rho"], 1.0)
        self.assertLess(r["p_valor"], 0.01)
        self.assertIsNone(estatistica.spearman_permutacao([1, 2], [2, 1])["rho"])

    def test_limiar_maior_nao_cria_livre(self):
        s = estatistica.sensibilidade_do_limiar(self.POP)
        self.assertLessEqual(s["0.20"]["pct"][t3.LIVRE], s["0.15"]["pct"][t3.LIVRE])
        self.assertLessEqual(s["0.15"]["pct"][t3.LIVRE], s["0.10"]["pct"][t3.LIVRE])


if __name__ == "__main__":
    unittest.main()
