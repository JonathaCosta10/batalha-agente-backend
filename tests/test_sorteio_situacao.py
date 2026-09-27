"""Sorteio por SITUAÇÃO financeira (dono 2026-09-27 14:39): perfil-usuario/definir/ {"usuario":"aleatorio"} e o
"Testar próximo perfil" do i-agora (sessao.trocar_cliente) sorteiam primeiro a situação, depois o id.

Provas negativas: o sorteio uniforme antigo NÃO alterna situações (reprova no mesmo teste que o novo passa);
situação forçada só sorteia dentro dela; categoria inválida 400 com as válidas; ficheiro ausente -> uniforme e
diz o motivo; `excluir` sempre respeitado; a regra do ficheiro é a mesma da abertura (domain.situacao_do_mes).
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")
import django  # noqa: E402

django.setup()

from django.test import Client  # noqa: E402

from apps.context_agent_datadriven.services import perfil_usuario as pu  # noqa: E402
from apps.i_agora import domain, sessao  # noqa: E402

BASE = "/api/v1/context-agent/perfil-usuario/"
NEG = [f"00000000-0000-4000-8000-00000000000{i}" for i in range(4)]
SOB = [f"00000000-0000-4000-8000-00000000001{i}" for i in range(6)]
SEM = "00000000-0000-4000-8000-000000000020"  # NAO_MEDIDO: nunca sai no sorteio por situação
TODOS = NEG + SOB + [SEM]
MAPA = {**{u: "fluxo_negativo" for u in NEG}, **{u: "sobra_observada" for u in SOB}, SEM: "NAO_MEDIDO"}
CSV = "indice,id_usuario,nome,genero,movimentos,meses,primeiro_anomes,ultimo_anomes\n" + "".join(
    f"{i},{u},Pessoa{i},F,10,12,202501,202512\n" for i, u in enumerate(TODOS, 1))


class Base(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        raiz = Path(self.pasta.name)
        self.csv = raiz / "usuarios_verdade.csv"
        self.csv.write_text(CSV, encoding="utf-8")
        self.arquivo = raiz / "situacao_por_usuario.json"
        self.arquivo.write_text(json.dumps({"selo": {}, "situacao": MAPA}), encoding="utf-8")
        self.patches = [patch.object(pu, "ARQUIVO_CSV", self.csv), patch.object(sessao, "ARQUIVO_SITUACAO", self.arquivo)]
        for p in self.patches:
            p.start()
        pu._base["mtime"] = None
        sessao._cache["chave"] = None

    def tearDown(self):
        for p in self.patches:
            p.stop()
        sessao._cache["chave"] = None
        pu._base["mtime"] = None
        self.pasta.cleanup()

    def cadeia(self, sortear, n=60):
        """n sorteios seguidos, cada um excluindo o anterior (o "Testar próximo perfil")."""
        atual, ids = None, []
        for _ in range(n):
            atual = sortear(atual)
            ids.append(atual)
        return ids


class SorteioPorSituacaoTest(Base):
    def test_alterna_situacao_e_prova_negativa_uniforme(self):
        ids = self.cadeia(lambda atual: sessao.sortear(exclude=atual))
        cats = [MAPA[u] for u in ids]
        self.assertTrue(all(a != b for a, b in zip(cats, cats[1:])), cats)  # sempre outra situação
        self.assertTrue(all(a != b for a, b in zip(ids, ids[1:])))
        self.assertNotIn(SEM, ids)
        # Prova negativa: a regra antiga (uniforme por id) repete situação em 60 passos (P(não) ~ 1e-14).
        antigo = self.cadeia(lambda atual: sessao._uniforme(TODOS, atual, "x")[0])
        cats_antigo = [MAPA[u] for u in antigo]
        self.assertTrue(any(a == b for a, b in zip(cats_antigo, cats_antigo[1:])))

    def test_modo_e_so_a_categoria(self):
        ref, sorteio = sessao.sortear_com_modo(exclude=NEG[0])
        self.assertEqual(sorteio, {"modo": "por_situacao", "situacao": "sobra_observada"})
        self.assertIn(ref, SOB)

    def test_forcada_so_dentro_dela_e_respeita_excluir(self):
        for _ in range(100):
            ref, sorteio = sessao.sortear_com_modo(exclude=NEG[1], situacao="fluxo_negativo")
            self.assertIn(ref, NEG)
            self.assertNotEqual(ref, NEG[1])
            self.assertEqual(sorteio["situacao"], "fluxo_negativo")
        self.assertEqual(len({sessao.sortear(situacao="fluxo_negativo", exclude=NEG[1]) for _ in range(200)}), 3)

    def test_categoria_invalida_ou_vazia(self):
        for cat in ("rico", "NAO_MEDIDO", "fluxo_equilibrado"):  # inexistente, não sorteável, sem ninguém
            with self.subTest(cat=cat), self.assertRaises(sessao.SituacaoInvalida) as erro:
                sessao.sortear(situacao=cat)
            self.assertEqual(erro.exception.validas, ["fluxo_negativo", "sobra_observada"])

    def test_excluir_sempre_respeitado(self):
        for atual in TODOS:
            for _ in range(30):
                self.assertNotEqual(sessao.sortear(exclude=atual), atual)
        # Catálogo de um só: devolve ele mesmo (não há outro), como antes.
        self.assertEqual(sessao.sortear([NEG[0]], exclude=NEG[0]), NEG[0])

    def test_ficheiro_ausente_uniforme_e_diz(self):
        self.arquivo.unlink()
        vistos = set()
        for _ in range(300):
            ref, sorteio = sessao.sortear_com_modo(exclude=SOB[0])
            self.assertEqual(sorteio, {"modo": "uniforme", "motivo": "situacao NAO_MEDIDA"})
            self.assertNotEqual(ref, SOB[0])
            vistos.add(ref)
        self.assertIn(SEM, vistos)  # uniforme de verdade: todo o catálogo
        with self.assertRaises(sessao.SituacaoNaoMedida):  # forçar sem medida não vira uniforme calado
            sessao.sortear(situacao="fluxo_negativo")

    def test_ficheiro_corrompido_conta_como_ausente(self):
        self.arquivo.write_text("{nao e json", encoding="utf-8")
        self.assertEqual(sessao.sortear_com_modo()[1]["modo"], "uniforme")

    def test_trocar_cliente_da_abertura_usa_o_mesmo_sorteio(self):
        trocas = []
        with patch.object(pu, "trocar_usuario", lambda sid, novo: trocas.append(novo)):
            ids = self.cadeia(lambda atual: sessao.trocar_cliente("sid", atual=atual), n=30)
        self.assertEqual(ids, trocas)
        cats = [MAPA[u] for u in ids]
        self.assertTrue(all(a != b for a, b in zip(cats, cats[1:])))


class DefinirHttpTest(Base):
    def setUp(self):
        super().setUp()
        self.http = Client()

    def post(self, corpo):
        return self.http.post(BASE + "definir/", corpo, content_type="application/json")

    def test_aleatorio_201_com_sorteio_e_alterna(self):
        atual, cats = NEG[0], []
        for _ in range(12):
            r = self.post({"usuario": "aleatorio", "excluir": atual})
            self.assertEqual(r.status_code, 201)
            corpo = r.json()
            self.assertEqual(corpo["sorteio"]["modo"], "por_situacao")
            self.assertEqual(set(corpo["sorteio"]), {"modo", "situacao"})  # só a categoria, nenhum valor
            novo = corpo["usuario"]["codigo"]
            self.assertNotEqual(novo, atual)
            self.assertEqual(MAPA[novo], corpo["sorteio"]["situacao"])
            cats.append(corpo["sorteio"]["situacao"])
            atual = novo
        self.assertTrue(all(a != b for a, b in zip(["fluxo_negativo"] + cats, cats)))

    def test_situacao_forcada_e_invalida_400(self):
        for _ in range(20):
            r = self.post({"usuario": "aleatorio", "situacao": "sobra_observada", "excluir": SOB[0]})
            self.assertEqual(r.status_code, 201)
            self.assertIn(r.json()["usuario"]["codigo"], SOB[1:])
        r = self.post({"usuario": "aleatorio", "situacao": "esbanjador"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["situacoes_validas"], ["fluxo_negativo", "sobra_observada"])
        self.assertNotIn("sessao_id", r.json())

    def test_uuid_explicito_nao_ganha_sorteio(self):
        r = self.post({"usuario": NEG[0]})
        self.assertEqual(r.status_code, 201)
        self.assertNotIn("sorteio", r.json())

    def test_sem_ficheiro_uniforme_com_motivo_e_forcada_503(self):
        self.arquivo.unlink()
        r = self.post({"usuario": "aleatorio", "excluir": NEG[0]})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["sorteio"], {"modo": "uniforme", "motivo": "situacao NAO_MEDIDA"})
        r = self.post({"usuario": "aleatorio", "situacao": "fluxo_negativo"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["estado"], "NAO_MEDIDO")


class RegraEFicheiroRealTest(unittest.TestCase):
    def test_regra_e_a_da_abertura(self):
        snap = {"reference_month": "2025-12", "inflows": "100.00", "outflows": "100.01", "categories": {},
                "client_ref": NEG[0], "seal": {"source": "t"}}
        with patch.object(domain, "nomes", lambda: {}):
            for entra, sai, cat in (("100", "100.01", "fluxo_negativo"), ("100", "100", "fluxo_equilibrado"),
                                    ("100", "99.99", "sobra_observada")):
                estado = domain.from_snapshot({**snap, "inflows": entra, "outflows": sai})
                self.assertEqual(estado["profile"]["situation"], cat)
                self.assertEqual(domain.situacao_do_mes(entra, sai), cat)

    def test_ficheiro_versionado_cobre_o_catalogo_com_selo(self):
        arquivo = Path(sessao.ARQUIVO_SITUACAO)
        if not arquivo.exists():
            self.skipTest("data/situacao_por_usuario.json ausente: NAO_MEDIDO (rode o script)")
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        self.assertEqual(set(dados["situacao"]), set(sessao.catalogo()))
        self.assertTrue(set(dados["situacao"].values()) <= set(domain.SITUACOES) | {"NAO_MEDIDO"})
        selo = dados["selo"]
        for campo in ("fonte", "regra", "gerado_em", "contagem"):
            self.assertIn(campo, selo)
        self.assertEqual(sum(selo["contagem"].values()), len(dados["situacao"]))


if __name__ == "__main__":
    unittest.main()
