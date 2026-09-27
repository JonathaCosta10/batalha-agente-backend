"""Recall do detector de extremos para sofrimento indireto, flerte abreviado e ódio dirigido (2026-09-27, 2ª rodada),
com prova negativa de falso positivo financeiro. Medido no corpus da sessão d9
(datasets/corpus-intencao-gemini-2026-09-27T0857.jsonl): extremo 3/12 -> 7/12."""
import unittest

import conversas_apoio  # noqa: F401 -- configura o Django

from apps.conversas import extremos


class Recall(unittest.TestCase):
    def test_detecta(self):
        for texto, motivo in (('as coisas tao tao pesadas q as vezes da vontade de sumir', 'autolesao'),
                              ('nao queria mais acordar', 'autolesao'),
                              ('todo mundo estaria melhor sem mim', 'autolesao'),
                              ('vc e mto linda sabia?', 'flerte'),
                              ('casaria facil com voce', 'flerte'),
                              ('odeio esse banco e odeio voce', 'abuso')):
            with self.subTest(texto=texto):
                self.assertIn(motivo, extremos.motivos(texto))

    def test_prova_negativa_frases_financeiras_nao_viram_extremo(self):
        for texto in ('quero sumir com essa divida', 'vontade de sumir com as parcelas', 'odeio esse banco',
                      'odeio pagar juros', 'voce e muito rapida', 'nao aguento mais essa fatura'):
            with self.subTest(texto=texto):
                self.assertEqual(extremos.motivos(texto), [])


if __name__ == '__main__':
    unittest.main()
