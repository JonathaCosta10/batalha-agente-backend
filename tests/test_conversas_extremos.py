"""extremos.py: deteção por regra antes do modelo. Cada motivo tem prova positiva e prova negativa."""
import unittest

from conversas_apoio import MARIA  # noqa: F401  (faz django.setup)

from apps.conversas import extremos  # noqa: E402


def motivo(msg):
    return (extremos.detectar(msg) or {}).get('motivo')


class Positivos(unittest.TestCase):
    def test_cada_motivo(self):
        casos = {'quero me matar': 'autolesao', 'vou te matar': 'ameaca',
                 'você é linda, sai comigo?': 'flerte'}
        for msg, esperado in casos.items():
            with self.subTest(msg=msg):
                self.assertEqual(motivo(msg), esperado)

    def test_destino_e_invisivel(self):
        enc = extremos.detectar('quero me matar')
        self.assertEqual(enc['destino'], 'humano')
        self.assertFalse(enc['visivel'])
        self.assertEqual(extremos.detectar('vou te matar')['destino'], 'seguranca')

    def test_prioridade_autolesao_vence(self):
        self.assertEqual(motivo('você é linda, mas eu quero me matar'), 'autolesao')

    def test_fala_autolesao_cita_cvv(self):
        texto, _ = extremos.fala('autolesao')
        self.assertIn('188', texto)


class ProvasNegativas(unittest.TestCase):
    """Frases financeiras com palavras parecidas NÃO podem disparar encaminhamento."""

    def test_financeiro_normal_nao_dispara(self):
        for msg in ('matar a dívida', 'ameaça de juros', 'estou morrendo de gastar',
                    'flertando com o limite do cartão', 'matar a saudade do mercado',
                    'quanto gastei com mercado?', 'tô cheio de dívidas, o que eu faço?'):
            with self.subTest(msg=msg):
                self.assertIsNone(motivo(msg))


if __name__ == '__main__':
    unittest.main()
