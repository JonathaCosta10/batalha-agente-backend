"""Especificação §3: T3 (Vulnerável, Esbanjador, Livre) com precedência Vulnerável > Esbanjador > Livre > sem segmento.

Módulo sob teste: services/metricas_fluxo.classificar_t3_spec. O T3 em produção é
pastas_raiz/estudos/i_agora/t3.classificar_t3 (e o CASE de visao_perfil_t3.sql:25-30, que é a mesma regra).
Prova negativa: Surplus < 0 nunca pode sair Livre nem Esbanjador; cheque especial ativo nunca pode sair Esbanjador.
Divergências com o T3 atual: @unittest.expectedFailure, com arquivo:linha.
"""

import unittest
from decimal import Decimal
from pathlib import Path

from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora import t3
from apps.context_agent_datadriven.services import metricas_fluxo as mf
from desafio_itau import politica


def mes(anomes, inflow, outflow, variavel=0, **kw):
    return {"anomes": anomes, "inflow": inflow, "outflow": outflow, "variavel": variavel, **kw}


def ano(inflow, outflow, variavel=0, n=12, **kw):
    return [mes(202500 + m, inflow, outflow, variavel, **kw) for m in range(1, n + 1)]


def seg(meses, **kw):
    return mf.classificar_t3_spec(meses, **kw)["segmento"]


class Constantes(unittest.TestCase):
    def test_limiar_15_igual_a_politica(self):
        self.assertEqual(Decimal(politica.parametro("t3.limiar_surplus", "limiar_fracao")) * 100, mf.LIMIAR_MARGEM_PCT)

    def test_precedencia_declarada(self):
        self.assertEqual(mf.PRECEDENCIA_T3, (mf.VULNERAVEL, mf.ESBANJADOR, mf.LIVRE))

    def test_rotulos_iguais_aos_do_t3_atual(self):
        self.assertEqual((mf.VULNERAVEL, mf.ESBANJADOR, mf.LIVRE), t3.SEGMENTOS)

    def test_decisoes_pendentes_existem_e_estao_marcadas(self):
        fonte = Path(mf.__file__).read_text(encoding="utf-8")
        for nome in mf.DECISOES_PENDENTES:
            self.assertTrue(hasattr(mf, nome), nome)
        # Decisão 2026-09-27 09:28 BRT: o dono aceitou as recomendações; o marcador virou DECIDIDO.
        self.assertGreaterEqual(fonte.count("DECIDIDO 2026-09-27 (dono aceitou a recomendação) ("), len(mf.DECISOES_PENDENTES) - 4)
        self.assertEqual(fonte.count("DECISAO_PENDENTE ("), 0)  # prova negativa: marcador antigo reprova


class Vulneravel(unittest.TestCase):
    def test_surplus_negativo(self):
        self.assertEqual(seg(ano(1000, 1100)), mf.VULNERAVEL)

    def test_margem_abaixo_de_15(self):
        self.assertEqual(seg(ano(1000, "850.01")), mf.VULNERAVEL)

    def test_margem_exatamente_15_nao_e_vulneravel(self):
        self.assertEqual(seg(ano(1000, 850)), mf.LIVRE)

    def test_cheque_especial_ativo_proxy_saldo(self):
        meses = ano(1000, 600)
        meses[-1]["uso_cheque_especial"] = True
        self.assertEqual(seg(meses), mf.VULNERAVEL)

    def test_juros_pagos_so_e_gatilho_com_a_leitura_alternativa(self):
        # Juros pagos: 695/1000 clientes; como gatilho OU leva 97,8 % do recorte N=316 a Vulnerável
        # (q_spec_diagnostico.json · 2026-09-27T09:17 BRT). Por padrão não é gatilho.
        meses = ano(1000, 600, juros_pagos=10, ma_divida=10)
        self.assertEqual(seg(meses), mf.LIVRE)
        self.assertEqual(seg(meses, juros_pagos_gatilho=True), mf.VULNERAVEL)

    def test_inflow_zero(self):
        self.assertEqual(seg(ano(0, 500)), mf.VULNERAVEL)
        self.assertEqual(seg(ano(0, 0)), mf.NAO_MEDIDO)
        self.assertEqual(seg([]), mf.NAO_MEDIDO)


class Esbanjador(unittest.TestCase):
    def test_fronteira_070_e_085(self):
        self.assertEqual(seg(ano(1000, 700, 200)), mf.ESBANJADOR)
        self.assertEqual(seg(ano(1000, 850, 300)), mf.ESBANJADOR)

    def test_fora_da_faixa(self):
        self.assertEqual(seg(ano(1000, 690, 200)), mf.LIVRE)          # 0,69
        self.assertEqual(seg(ano(1000, "850.1", 300)), mf.VULNERAVEL)  # 0,8501 => margem < 15 %

    def test_variavel_baixo_nao_e_esbanjador(self):
        # 100/800 = 0,125 < 0,1593 (mediana medida, q_spec_diagnostico.json · 09:17 BRT)
        self.assertEqual(seg(ano(1000, 800, 100)), mf.LIVRE)

    def test_inflow_medio_alto_sem_limiar_fica_pendente(self):
        r = mf.classificar_t3_spec(ano(1000, 800, 300))
        self.assertIn("inflow_medio_alto_nao_avaliado", r["pendencias"])
        self.assertEqual(seg(ano(1000, 800, 300), inflow_medio_min=5000), mf.LIVRE)
        self.assertEqual(seg(ano(1000, 800, 300), inflow_medio_min=1000), mf.ESBANJADOR)

    def test_precedencia_vulneravel_sobre_esbanjador(self):
        meses = ano(1000, 800, 300)
        meses[-1]["credito_emergencial"] = 50
        r = mf.classificar_t3_spec(meses)
        self.assertEqual(r["segmento"], mf.VULNERAVEL)

    def test_precedencia_esbanjador_sobre_livre(self):
        r = mf.classificar_t3_spec(ano(1000, 800, 300))
        self.assertEqual(r["candidatos"], [mf.ESBANJADOR, mf.LIVRE])
        self.assertEqual(r["segmento"], mf.ESBANJADOR)


class Livre(unittest.TestCase):
    @staticmethod
    def estaveis(k):
        """k meses com margem 90 %, 12-k com margem 13 %; margem da janela > 15 %, razão ~0,74, variável 0."""
        return [mes(202500 + m, 1000, 100 if m <= k else 870) for m in range(1, 13)]

    def test_estavel_2_contra_3_meses(self):
        self.assertEqual(seg(self.estaveis(3)), mf.LIVRE)
        self.assertEqual(seg(self.estaveis(2)), mf.SEM_SEGMENTO)

    def test_divida_cara_10pct(self):
        self.assertEqual(seg(ano(1000, 600, ma_divida="99.99")), mf.LIVRE)
        self.assertEqual(seg(ano(1000, 600, ma_divida=100)), mf.SEM_SEGMENTO)

    def test_credito_emergencial_antigo_impede_livre(self):
        meses = ano(1000, 600)
        meses[0]["uso_cheque_especial"] = True  # fora dos 3 meses recentes: não é "ativo", mas não é "sem crédito"
        self.assertEqual(seg(meses), mf.SEM_SEGMENTO)


class BuracoDaEspecificacao(unittest.TestCase):
    def test_existe_cliente_sem_segmento(self):
        """A especificação não cobre todos: margem 40 %, sem crédito emergencial, dívida cara 12 % do Inflow
        não é Vulnerável (margem >= 15 %), nem Esbanjador (razão 0,60), nem Livre (dívida cara >= 10 %).
        Na base: 8,4 % sem segmento em jan–nov (84/1000 · q_spec_diagnostico.json · 2026-09-27T09:17 BRT)."""
        r = mf.classificar_t3_spec(ano(1000, 600, ma_divida=120))
        self.assertEqual(r["segmento"], mf.SEM_SEGMENTO)
        self.assertEqual(r["candidatos"], [])


class ProvaNegativa(unittest.TestCase):
    def test_surplus_negativo_nunca_livre_nem_esbanjador(self):
        for outflow in (1001, 1200, 5000):
            for variavel in (0, 300, 900):
                self.assertEqual(seg(ano(1000, outflow, variavel)), mf.VULNERAVEL)

    def test_cheque_especial_nunca_esbanjador(self):
        meses = ano(1000, 800, 300)
        meses[5]["uso_cheque_especial"] = True
        self.assertNotEqual(seg(meses), mf.ESBANJADOR)


class DivergenciaComT3Atual(unittest.TestCase):
    """t3.classificar_t3(inflow, outflow, discricionario) sobre médias mensais (t3.py:96-108)."""

    def test_concorda_surplus_negativo(self):
        self.assertEqual(t3.classificar_t3(1000, 1100, 0), seg(ano(1000, 1100)))

    def test_concorda_inflow_zero(self):
        self.assertEqual(t3.classificar_t3(0, 500, 0), seg(ano(0, 500)))

    def test_concorda_margem_exatamente_15_estavel(self):
        self.assertEqual(t3.classificar_t3(1000, 850, 0), seg(ano(1000, 850)))

    @unittest.expectedFailure
    def test_margem_10_com_discricionario_e_vulneravel(self):
        """DIVERGE. t3.py:106-107 (e visao_perfil_t3.sql:28): margem < 15 % mas (surplus + discricionário)/inflow
        >= 15 % => Esbanjador. Especificação: margem < 15 % => Vulnerável."""
        self.assertEqual(seg(ano(1000, 900, 100)), mf.VULNERAVEL)
        self.assertEqual(t3.classificar_t3(1000, 900, 100), t3.VULNERAVEL)

    @unittest.expectedFailure
    def test_razao_080_com_variavel_alto_e_esbanjador(self):
        """DIVERGE. t3.py:104-105 (e visao_perfil_t3.sql:27): margem >= 15 % => Livre antes de olhar a razão.
        Especificação: Outflow/Inflow em [0,70; 0,85] com gasto discricionário alto => Esbanjador."""
        self.assertEqual(seg(ano(1000, 800, 300)), mf.ESBANJADOR)
        self.assertEqual(t3.classificar_t3(1000, 800, 300), t3.ESBANJADOR)

    @unittest.expectedFailure
    def test_cheque_especial_ativo_e_vulneravel(self):
        """DIVERGE. t3.py:96 não recebe crédito/cheque especial (nem o CASE de visao_perfil_t3.sql:25-30):
        margem 25 % com cheque especial ativo sai Livre. Especificação: uso ativo de cheque especial => Vulnerável."""
        meses = ano(1000, 750)
        meses[-1]["uso_cheque_especial"] = True
        self.assertEqual(seg(meses), mf.VULNERAVEL)
        self.assertEqual(t3.classificar_t3(1000, 750, 0), t3.VULNERAVEL)

    @unittest.expectedFailure
    def test_livre_exige_estabilidade_em_3_meses(self):
        """DIVERGE. t3.py:104 decide Livre só pela margem MÉDIA da janela; não conta meses estáveis nem dívida
        cara. Especificação: margem >= 15 % em >= 3 meses. Caso: 2 meses estáveis, média ~25,8 %."""
        meses = Livre.estaveis(2)
        media_in = sum(m["inflow"] for m in meses) / 12
        media_out = sum(m["outflow"] for m in meses) / 12
        self.assertNotEqual(seg(meses), mf.LIVRE)
        self.assertNotEqual(t3.classificar_t3(media_in, media_out, 0), t3.LIVRE)


if __name__ == "__main__":
    unittest.main()
