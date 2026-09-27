"""Controle da conversa: o roteiro real passa na validação; roteiros ruins sintéticos reprovam."""

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")
import django  # noqa: E402

django.setup()

from django.test import Client  # noqa: E402

from apps.context_agent_datadriven.views_controle_conversa import ARQUIVO_ROTEIRO, carregar_roteiro  # noqa: E402

URL = "/api/v1/context-agent/controle-conversa/"


def _roteiro_com(falas):
    base = json.loads(ARQUIVO_ROTEIRO.read_text(encoding="utf-8"))
    arquivo = Path(tempfile.mkdtemp()) / "roteiro.json"
    arquivo.write_text(json.dumps({**base, "falas": falas}), encoding="utf-8")
    return arquivo


class ControleConversaTest(unittest.TestCase):
    def test_roteiro_real_contem_as_falas_das_telas(self):
        roteiro = carregar_roteiro()
        textos = json.dumps(roteiro, ensure_ascii=False)
        for trecho in ("Olá, {primeiro_nome}", "Que bom ter você aqui, {primeiro_nome}!", "regra *50-30-20*",
                       "Topo o desafio", "Meu delivery vai sentir saudade. Meus planos vão agradecer.",
                       "Este card não mostra seu saldo, sua renda nem os valores do plano."):
            self.assertIn(trecho, textos)

    def test_rota_filtra_por_estagio(self):
        corpo = Client().get(URL + "?estagio=card").json()
        self.assertTrue(corpo["falas"])
        self.assertEqual({f["estagio"] for f in corpo["falas"]}, {"card"})
        self.assertEqual(Client().get(URL + "?estagio=nada").status_code, 400)

    def test_roteiro_cobre_o_inventario_do_front(self):
        """falas-fixas.md (front 1ca06b5): 188 linhas = 189 ids (card.alt_itau / card.alt_iagora na mesma linha)."""
        roteiro = carregar_roteiro()
        self.assertGreaterEqual(len(roteiro["falas"]), 188)
        inventario = [i for f in roteiro["falas"] for i in f.get("inventario_front", [])]
        self.assertEqual(len(inventario), len(set(inventario)), "id do inventário mapeado duas vezes")
        self.assertEqual(len(inventario), 189)
        ids = {f["id"] for f in roteiro["falas"]}
        de_para = {i: f["id"] for f in roteiro["falas"] for i in f.get("inventario_front", [])}
        for inv, rid in {"bot.apoio_negativado": "bot.apoio_negativado", "home.aviso_negativado": "home.aviso_negativado",
                         "bot.humano_negativado": "bot.humano_negativado", "bot.convite": "bot.convite_50_30_20",
                         "card.frase.reserve.0": "card.frase.reserva.0", "intro.aria_agora": "intro.gatilho_agora",
                         "proposta.rodape": "confirm.proposta.rodape", "acomp.titulo": "acompanhe.titulo",
                         "doc.descricao": "global.doc.descricao"}.items():
            self.assertEqual(de_para.get(inv), rid)
        self.assertTrue(set(de_para.values()) <= ids)

    def test_frase_da_reserva_tem_variante_por_genero(self):
        falas = {f["id"]: f for f in carregar_roteiro()["falas"]}
        fala = falas["card.frase.reserva.0"]
        self.assertIn("genero", fala["variaveis"])
        self.assertEqual(set(fala["texto"]), {"F", "M"})
        self.assertTrue(fala["texto"]["F"].endswith("preparada."))
        self.assertTrue(fala["texto"]["M"].endswith("preparado."))
        self.assertIn("genero", falas["card.frases"]["variaveis"])

    def test_rota_devolve_versao_roteiro_por_fala(self):
        corpo = Client().get(URL + "?estagio=acompanhe").json()
        self.assertEqual(corpo["versao_roteiro"], corpo["versao"])
        for fala in corpo["falas"]:
            self.assertEqual(fala["versao_roteiro"], corpo["versao"])
            self.assertIsInstance(fala["variaveis"], list)
            self.assertTrue(fala["texto"])

    # --- provas negativas ---
    def test_id_duplicado_reprova(self):
        fala = {"id": "x", "estagio": "home", "texto": "a"}
        with self.assertRaisesRegex(ValueError, "id duplicado"):
            carregar_roteiro(_roteiro_com([fala, fala]))

    def test_estagio_desconhecido_e_variavel_sem_fonte_reprovam(self):
        with self.assertRaisesRegex(ValueError, "estágio desconhecido"):
            carregar_roteiro(_roteiro_com([{"id": "y", "estagio": "tela9", "texto": "a"}]))
        with self.assertRaisesRegex(ValueError, "variável sem fonte"):
            carregar_roteiro(_roteiro_com([{"id": "z", "estagio": "home", "texto": "{cpf}", "variaveis": ["cpf"]}]))

    # --- Encaminhamento em extremos (estágio "extremo", contrato §4.9) ---
    IDS_EXTREMO = {"extremo.flerte", "extremo.ameaca", "extremo.autolesao", "extremo.abuso",
                   "extremo.encaminhamento_humano"}

    def test_falas_de_extremo_tem_destino_motivo_e_nao_aparecem(self):
        extremos = [f for f in carregar_roteiro()["falas"] if f["estagio"] == "extremo"]
        self.assertEqual({f["id"] for f in extremos}, self.IDS_EXTREMO)
        for fala in extremos:
            self.assertIn(fala["destino"], {"humano", "seguranca"}, fala["id"])
            self.assertIn(fala["motivo"], {"flerte", "ameaca", "autolesao", "abuso", "extremo_financeiro"}, fala["id"])
            self.assertIs(fala["visivel"], False, fala["id"])
            self.assertEqual(fala["tipo"], "fixo", fala["id"])
            self.assertIn("o modelo nunca redige", fala["regra"])

    def test_ameaca_vai_para_seguranca_e_autolesao_cita_cvv(self):
        por_id = {f["id"]: f for f in carregar_roteiro()["falas"]}
        self.assertEqual(por_id["extremo.ameaca"]["destino"], "seguranca")
        self.assertIn("equipe de segurança", por_id["extremo.ameaca"]["texto"])
        self.assertIn("188", por_id["extremo.autolesao"]["texto"])
        self.assertEqual(por_id["extremo.flerte"]["texto"],
                         "Não vai dar, sou uma máquina 😄 Mas posso te ajudar com o seu plano.")
        prioridades = sorted((f["prioridade"], f["motivo"]) for f in por_id.values() if f["estagio"] == "extremo")
        self.assertEqual([m for _, m in prioridades],
                         ["autolesao", "ameaca", "abuso", "flerte", "extremo_financeiro"])

    def test_extremo_sem_destino_ou_visivel_reprova(self):
        """Prova negativa: fala de extremo mal formada tem de reprovar na carga do roteiro."""
        base = {"id": "extremo.x", "estagio": "extremo", "tipo": "fixo", "texto": "a", "motivo": "flerte",
                "destino": "humano", "visivel": False}
        carregar_roteiro(_roteiro_com([base]))  # controle: a forma boa passa
        sem_destino = {k: v for k, v in base.items() if k != "destino"}
        with self.assertRaisesRegex(ValueError, "extremo sem destino"):
            carregar_roteiro(_roteiro_com([sem_destino]))
        with self.assertRaisesRegex(ValueError, "visivel=false"):
            carregar_roteiro(_roteiro_com([{**base, "visivel": True}]))
        with self.assertRaisesRegex(ValueError, "extremo sem motivo"):
            carregar_roteiro(_roteiro_com([{**base, "motivo": "outro"}]))
        with self.assertRaisesRegex(ValueError, "ameaça vai para segurança"):
            carregar_roteiro(_roteiro_com([{**base, "motivo": "ameaca", "destino": "humano"}]))


if __name__ == "__main__":
    unittest.main()
