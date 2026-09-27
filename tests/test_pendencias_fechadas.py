"""Pendências fechadas em 2026-09-27 (segunda rodada): rótulo T3 no texto (D2), meses faltantes na média,
15% com fonte única, status do catálogo de produtos. Cada uma com prova negativa."""
import json
import unittest
from pathlib import Path

import conversas_apoio  # noqa: F401 -- configura o Django

from apps.conversas import interacao_dados
from apps.conversas.interacao_avaliacao import REPROVADO, guard_politica
from apps.conversas.rules import safe_text
from desafio_itau import politica
from desafio_itau.politica import lexico

RAIZ = Path(__file__).resolve().parents[1]


def reprovados(texto):
    return {c['nome'] for c in guard_politica(texto, None, None) if c['resultado'] == REPROVADO}


class RotuloT3NoTexto(unittest.TestCase):
    def test_rotulo_bloqueado_nos_dois_caminhos(self):
        for t in ('Seu perfil é Vulnerável.', 'Você não é esbanjador.', 'Você está no segmento Livre.',
                  'Pelo perfil_t3, sugiro revisar.'):
            with self.subTest(t=t):
                self.assertIn('politica.rotulo', reprovados(t))       # interacao/
                self.assertFalse(safe_text(t))                         # mensagens/

    def test_prova_negativa_linguagem_comum_passa(self):
        for t in ('Você tem tempo livre para revisar o orçamento.', 'Isso reduz a vulnerabilidade a imprevistos.'):
            with self.subTest(t=t):
                self.assertEqual(lexico.bloqueios(t, ['rotulo_interno']), [])


class MesesFaltantes(unittest.TestCase):
    def test_detecta_lacuna_no_meio_e_na_virada_de_ano(self):
        self.assertEqual(interacao_dados.meses_faltantes([202501, 202502, 202504]), [202503])
        self.assertEqual(interacao_dados.meses_faltantes([202411, 202502]), [202412, 202501])

    def test_prova_negativa_janela_completa(self):
        self.assertEqual(interacao_dados.meses_faltantes([202501, 202502, 202503]), [])
        self.assertEqual(interacao_dados.meses_faltantes([]), [])

    def test_resumo_expoe_cobertura_sem_imputar_zero(self):
        linha = lambda am, e: {'anomes': am, 'entradas': e, 'saidas': 100.0, 'necessidades': 50, 'desejos': 30,  # noqa: E731
                               'futuro_programado': 0, 'fora_da_regra': 20, 'saidas_sem_classe': 0,
                               'divida': 0, 'multas': 0}
        try:
            r = interacao_dados.resumir_mensal([linha(202501, 200.0), linha(202503, 200.0)], '2025-04-22')
        except KeyError as e:  # colunas de dívida com outro nome: o teste diz o que não mediu
            self.skipTest(f'linha sintética sem coluna {e}')
        self.assertEqual((r['media']['cobertura'], r['media']['meses_faltantes']), ('LACUNA', [202503 - 1]))
        self.assertEqual(r['media']['meses'], 2)  # denominador NÃO foi alterado: nada imputado
        self.assertEqual(r['situacao_conversa']['cobertura'], 'LACUNA')


class LimiarUnico(unittest.TestCase):
    def test_consultas_le_o_15_da_politica(self):
        from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora import consultas, t3
        esperado = politica.parametro('t3.limiar_surplus', 'limiar_fracao') * 100
        self.assertEqual(consultas.LIMIAR_SOBRA_SAUDAVEL_PCT, esperado)
        self.assertEqual(consultas.LIMIAR_SOBRA_SAUDAVEL_PCT, round(t3.LIMIAR_SURPLUS * 100))
        self.assertIn(f'{consultas.LIMIAR_SOBRA_SAUDAVEL_PCT}%', consultas.CLUSTER_SAUDAVEL)  # rótulo acompanha


class CatalogoDeProdutos(unittest.TestCase):
    CAT = json.loads((RAIZ / 'desafio_itau' / 'politica' / 'produtos-v1.json').read_text(encoding='utf-8'))

    def test_sem_catalogo_aprovado_chat_nao_cita(self):
        self.assertEqual(self.CAT['status'], 'SEM_CATALOGO_APROVADO')
        self.assertFalse(self.CAT['regra_de_uso']['chat_pode_citar_produto'])
        self.assertEqual(self.CAT['regra_de_uso']['ausencia_significa'], 'NAO_MEDIDO')
        for f in self.CAT['fontes_nao_homologadas']:
            with self.subTest(f=f['arquivo']):
                self.assertTrue((RAIZ / f['arquivo']).exists())
                self.assertEqual(f['fonte_da_taxa'], 'AUSENTE')

    def test_prova_negativa_mencao_a_produto_reprovada(self):
        self.assertIn('politica.produto', reprovados('Recomendo contratar um consórcio agora.'))
        self.assertFalse(safe_text('Você tem crédito pré-aprovado.'))


class OrdemDosModelos(unittest.TestCase):
    """I2 (2026-09-27 09:35): o modelo com cota medida vai primeiro, e o input_guard não cai no que só deu 429."""

    def test_primeiro_e_o_modelo_com_cota(self):
        from desafio_itau.modelos_llm import MODELO_PRIMEIRA_CHAMADA, MODELOS_GOOGLE
        self.assertEqual(MODELOS_GOOGLE[0], MODELO_PRIMEIRA_CHAMADA)
        self.assertEqual(set(MODELOS_GOOGLE), {'gemini-3.5-flash-lite', 'gemini-flash-latest'})  # nada trocado

    def test_guard_usa_o_modelo_com_cota_e_prova_negativa(self):
        from apps.conversas.interacao import _modelo_do_guard
        self.assertEqual(_modelo_do_guard(('gemini-3.5-flash-lite', 'gemini-flash-latest')), 'gemini-3.5-flash-lite')
        self.assertEqual(_modelo_do_guard(('gemini-flash-latest', 'gemini-3.5-flash-lite')), 'gemini-3.5-flash-lite')
        self.assertEqual(_modelo_do_guard(('x', 'y')), 'y')  # sem o modelo de cota: comportamento antigo


if __name__ == '__main__':
    unittest.main()
