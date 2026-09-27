"""estado.numeros_sem_fonte com fato NEGATIVO (cash_flow). Caso real 2026-09-27 11:34 (:8012, usuário 00108ccd):
"O que eu faço com as sobras?" -> o Gemini escreveu o fluxo de -1729.62 como "negativo de R$ 1729,62" e o guard
reprovava (503). O conserto aceita a magnitude só quando o texto marca o sinal; a inversão de sinal segue reprovada."""
import unittest

from apps.conversas import estado

CTX = {'facts': [{'id': 'inflows', 'value': '8201.83'}, {'id': 'outflows', 'value': '9931.45'},
                 {'id': 'cash_flow', 'value': '-1729.62'}, {'id': 'taxa_surplus_pct', 'value': '-21.09'}]}


class NumerosComSinalNegativoTest(unittest.TestCase):
    # Casos reais (texto do Gemini registado no :8012), que antes davam 503.
    def test_real_negativo_por_extenso_passa(self):
        texto = ('suas entradas médias foram de R$ 8201,83 por mês e suas saídas médias foram de R$ 9931,45 por mês, '
                 'resultando em um fluxo de caixa médio negativo de R$ 1729,62 por mês.')
        self.assertEqual(estado.numeros_sem_fonte(texto, CTX), [])

    def test_real_sinal_colado_passa(self):
        texto = ('a média mensal de entradas foi de R$ 8.201,83 e a de saídas foi de R$ 9.931,45, resultando em um '
                 'fluxo líquido médio de -R$ 1.729,62 por mês.')
        self.assertEqual(estado.numeros_sem_fonte(texto, CTX), [])

    def test_deficit_e_percentual_negativo_passam(self):
        self.assertEqual(estado.numeros_sem_fonte('Há um déficit de R$ 1.729,62 por mês (-21,09%).', CTX), [])

    # Provas negativas: o guard TEM de continuar a reprovar.
    def test_inversao_de_sinal_reprova(self):
        self.assertEqual(estado.numeros_sem_fonte('Sobram R$ 1.729,62 por mês para investir.', CTX), ['R$ 1.729,62'])

    def test_marcador_negativo_desfeito_por_palavra_positiva_reprova(self):
        texto = 'Nada de fluxo negativo: você tem uma sobra de R$ 1.729,62 por mês.'
        self.assertEqual(estado.numeros_sem_fonte(texto, CTX), ['R$ 1.729,62'])

    def test_marcador_em_outra_frase_nao_vale(self):
        texto = 'O fluxo foi negativo. Você guarda R$ 1.729,62 por mês.'
        self.assertEqual(estado.numeros_sem_fonte(texto, CTX), ['R$ 1.729,62'])

    def test_numero_inventado_com_marcador_reprova(self):
        self.assertEqual(estado.numeros_sem_fonte('Fluxo negativo de R$ 1.500,00 por mês.', CTX), ['R$ 1.500,00'])

    def test_marcador_negativo_nao_sustenta_magnitude_sem_fato(self):
        self.assertEqual(estado.numeros_sem_fonte('Déficit de R$ 9.000,00.', CTX), ['R$ 9.000,00'])


if __name__ == '__main__':
    unittest.main()
