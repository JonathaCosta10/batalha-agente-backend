"""Provas negativas para não aprovar uma conversa com fatos trocados."""

import copy
import unittest

from apps.context_agent_datadriven.services.qualidade_fluxo import verificar_fluxo


class QualidadeFluxoTest(unittest.TestCase):
    def setUp(self):
        self.cliente = {"id": 1, "nome": "Alexandre", "genero": "M", "score_comportamental": 187}
        self.chat = {
            "cliente": {"id": 1, "nome": "Alexandre"},
            "chave_interacao_tela_iai": "ON",
            "chat_variavel_1": {
                "texto_ativo": {"tag": "TEXTO_1[NEUTRO]", "texto_completo": "Mensagem inicial"},
                "mensagem_abertura": "Mensagem inicial",
                "botao_proximo": "E agora?",
            },
        }
        self.comunicacao = {
            "cliente": {"id": 1, "nome": "Alexandre", "score_comportamental": 187},
            "template_id": "TEMPLATE_3_FIXED_SPREADSHEET",
            "planilha_fixa": [{"score_minimo": 300, "status_elegibilidade": "Em Análise"}],
        }

    def test_fluxo_coerente(self):
        self.assertTrue(all(verificar_fluxo(self.cliente, self.chat, self.comunicacao).values()))

    def test_prova_negativa_outro_cliente_reprova(self):
        chat = copy.deepcopy(self.chat)
        chat["cliente"]["id"] = 2
        self.assertFalse(verificar_fluxo(self.cliente, chat, self.comunicacao)["mesmo_cliente_nas_tres_rotas"])

    def test_prova_negativa_tag_errada_reprova(self):
        chat = copy.deepcopy(self.chat)
        chat["chat_variavel_1"]["texto_ativo"]["tag"] = "TEXTO_2[MASCULINO]"
        self.assertFalse(verificar_fluxo(self.cliente, chat, self.comunicacao)["tag_respeita_chave_e_genero"])

    def test_prova_negativa_preaprovacao_sem_score_reprova(self):
        comunicacao = copy.deepcopy(self.comunicacao)
        comunicacao["planilha_fixa"][0]["status_elegibilidade"] = "Pré-Aprovado"
        self.assertFalse(verificar_fluxo(self.cliente, self.chat, comunicacao)["elegibilidade_coerente"])
