"""Especificação §5: tom por perfil, testado de forma determinística (sem modelo).

Vulnerável: acolhedor, não julgador, estabilizar, cortar supérfluos, eliminar o cheque especial.
Esbanjador: provocativo, trade-offs, impacto futuro.   Livre: consultivo, investimento, reserva, patrimônio.
Eixos e proibidos: metricas_fluxo.TOM_SPEC. O "corpus" de um perfil em produção = tom + foco + exigidos de
t3.PERFIS_DE_RESPOSTA (t3.py:113-138) + mensagens-base de fluxos_comportamento.json + COMPLEMENTO_TOM
(apps/conversas/interacao.py:431-433) — é o que chega ao prompt (interacao.liquid:5-7).
Prova negativa: "Você é esbanjador" e texto julgador TÊM de reprovar.
Divergências: @unittest.expectedFailure com arquivo:linha.
"""

import json
import os
import unittest
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")
import django  # noqa: E402

django.setup()

from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora import t3  # noqa: E402
from apps.context_agent_datadriven.services import metricas_fluxo as mf  # noqa: E402
from desafio_itau.politica import lexico  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
FLUXOS = json.loads((RAIZ / "apps" / "conversas" / "fluxos_comportamento.json").read_text(encoding="utf-8"))["fluxos"]
LIQUID = (RAIZ / "apps" / "conversas" / "prompts" / "interacao.liquid").read_text(encoding="utf-8").splitlines()
BLOCO_VAZIO = {"meses": [], "anos": [], "categorias": [], "texto_permitido": ""}


def corpus(segmento):
    from apps.conversas.interacao import COMPLEMENTO_TOM
    p = t3.PERFIS_DE_RESPOSTA[segmento]
    partes = [p["tom"], p["foco"], " ".join(p["exigidos_um_de"]), COMPLEMENTO_TOM[segmento]]
    partes += [f["mensagem_base"] for f in FLUXOS[segmento].values()]
    return " ".join(partes)


def falta(segmento, eixo):
    return eixo in mf.avaliar_tom(corpus(segmento), segmento)["faltam"]


class Especificacao(unittest.TestCase):
    BONS = {
        mf.VULNERAVEL: ("Com acolhimento e sem pressa: o primeiro passo é estabilizar o mês, cortar supérfluos e "
                        "eliminar o cheque especial."),
        mf.ESBANJADOR: ("Uma provocação: cada delivery é uma troca. Em vez de pedir, pense no impacto no seu futuro "
                        "— o trade-off é seu."),
        mf.LIVRE: ("Em tom consultivo: com a reserva formada, dá para estudar investimento e construir patrimônio."),
    }

    def test_tres_perfis_com_eixos(self):
        self.assertEqual(set(mf.TOM_SPEC), {mf.VULNERAVEL, mf.ESBANJADOR, mf.LIVRE})
        self.assertEqual(set(mf.TOM_SPEC[mf.ESBANJADOR]["eixos"]), {"provocativo", "trade_offs", "impacto_futuro"})

    def test_textos_bons_passam(self):
        for seg, texto in self.BONS.items():
            self.assertTrue(mf.avaliar_tom(texto, seg)["aprovado"], (seg, mf.avaliar_tom(texto, seg)))

    # --- prova negativa
    def test_rotulo_e_julgamento_reprovam(self):
        r = mf.avaliar_tom(self.BONS[mf.ESBANJADOR] + " Você é esbanjador.", mf.ESBANJADOR)
        self.assertFalse(r["aprovado"])
        self.assertIn("esbanjador", r["proibidos"])
        r = mf.avaliar_tom(self.BONS[mf.VULNERAVEL] + " A culpa é sua, foi irresponsável.", mf.VULNERAVEL)
        self.assertFalse(r["aprovado"])
        self.assertTrue(lexico.bloqueios("Você é esbanjador."))
        self.assertTrue(lexico.bloqueios("Você é irresponsável com dinheiro."))

    def test_texto_sem_eixo_reprova(self):
        self.assertIn("patrimonio", mf.avaliar_tom("Vale formar uma reserva e investir.", mf.LIVRE)["faltam"])


class CodigoAtualBate(unittest.TestCase):
    def test_vulneravel_acolhedor(self):
        self.assertFalse(falta(mf.VULNERAVEL, "acolhedor"))

    def test_livre_consultivo_reserva_investimento(self):
        for eixo in ("consultivo", "reserva", "investimento"):
            self.assertFalse(falta(mf.LIVRE, eixo), eixo)

    def test_nenhum_perfil_usa_proibido_nem_julgamento(self):
        for seg in (mf.VULNERAVEL, mf.ESBANJADOR, mf.LIVRE):
            self.assertEqual(mf.avaliar_tom(corpus(seg), seg)["proibidos"], [], seg)
            for f in FLUXOS[seg].values():
                achados = [a for a in lexico.bloqueios(f["mensagem_base"])
                           if a["categoria"] in ("julgamento", "rotulo_interno")]
                self.assertEqual(achados, [], f["id"])


class DivergenciaVulneravel(unittest.TestCase):
    @unittest.expectedFailure
    def test_estabilizar(self):
        """DIVERGE. Nem t3.py:114-121 nem fluxos_comportamento.json:12-64 nem interacao.py:431 falam em
        estabilizar; o foco é "renegociar antes de cortar essencial" (t3.py:118)."""
        self.assertFalse(falta(mf.VULNERAVEL, "estabilizar"))

    @unittest.expectedFailure
    def test_cortar_superfluos(self):
        """DIVERGE. t3.py:118 manda renegociar ANTES de cortar; nenhum texto do Vulnerável cita supérfluos
        (fluxos_comportamento.json:12-64)."""
        self.assertFalse(falta(mf.VULNERAVEL, "cortar_superfluos"))

    @unittest.expectedFailure
    def test_eliminar_cheque_especial(self):
        """DIVERGE. Nenhum texto do Vulnerável cita cheque especial (t3.py:114-121, fluxos_comportamento.json:12-64);
        a base nem tem a categoria (q_spec_diagnostico.json · 2026-09-27T09:17 BRT)."""
        self.assertFalse(falta(mf.VULNERAVEL, "eliminar_cheque_especial"))

    @unittest.expectedFailure
    def test_guard_aceita_orientacao_de_eliminar_cheque_especial(self):
        """DIVERGE. interacao_avaliacao.py:284-286 lista "cheque especial" em PRODUTOS e :312-313 reprova
        `alucinacao.produto` quando o termo não está no bloco: a orientação exigida pela especificação é barrada."""
        from apps.conversas.interacao_avaliacao import APROVADO, guard_alucinacao
        checagens = guard_alucinacao("Vamos eliminar o cheque especial, passo a passo.", BLOCO_VAZIO)
        produto = next(c for c in checagens if c["nome"] == "alucinacao.produto")
        self.assertEqual(produto["resultado"], APROVADO)


class DivergenciaEsbanjador(unittest.TestCase):
    @unittest.expectedFailure
    def test_provocativo(self):
        """DIVERGE. t3.py:123: tom "direto e encorajador", não provocativo.
        divergência DECIDIDA: D-17/D-18, o código atual é o comportamento aprovado (D-18, 2026-09-27: direto, com trade-offs, sem provocar)."""
        self.assertFalse(falta(mf.ESBANJADOR, "provocativo"))

    @unittest.expectedFailure
    def test_trade_offs(self):
        """DIVERGE. t3.py:122-129 e fluxos_comportamento.json:65-125 pedem limite/ajuste por mês, sem trade-off
        explícito (troca, em vez de, custo de oportunidade)."""
        self.assertFalse(falta(mf.ESBANJADOR, "trade_offs"))

    @unittest.expectedFailure
    def test_impacto_futuro(self):
        """DIVERGE. Nenhum texto do Esbanjador fala de futuro/longo prazo (t3.py:122-129,
        fluxos_comportamento.json:65-125, interacao.py:432)."""
        self.assertFalse(falta(mf.ESBANJADOR, "impacto_futuro"))


class DivergenciaLivre(unittest.TestCase):
    @unittest.expectedFailure
    def test_patrimonio(self):
        """DIVERGE. Nenhum texto do Livre fala de patrimônio (t3.py:130-137, fluxos_comportamento.json:126-181)."""
        self.assertFalse(falta(mf.LIVRE, "patrimonio"))

    @unittest.expectedFailure
    def test_prompt_nao_proibe_investimento(self):
        """DIVERGE. interacao.liquid:18 proíbe recomendar ou oferecer investimento a TODOS os perfis; a especificação
        quer o Livre orientado a investimento.
        divergência DECIDIDA: D-17/D-18, o código atual é o comportamento aprovado (D-17, 2026-09-27: mantém a proibição, BCB RC 8/2023)."""
        self.assertNotIn("investimento", LIQUID[17])

    @unittest.expectedFailure
    def test_guard_aceita_falar_de_investimento(self):
        """DIVERGE. interacao_avaliacao.py:284-286 lista "investimento" em PRODUTOS; :312-313 reprova o texto.
        divergência DECIDIDA: D-17/D-18, o código atual é o comportamento aprovado (D-17, 2026-09-27: mantém a proibição, BCB RC 8/2023)."""
        from apps.conversas.interacao_avaliacao import APROVADO, guard_alucinacao
        checagens = guard_alucinacao("Com a reserva formada, vale planejar o investimento.", BLOCO_VAZIO)
        produto = next(c for c in checagens if c["nome"] == "alucinacao.produto")
        self.assertEqual(produto["resultado"], APROVADO)


if __name__ == "__main__":
    unittest.main()
