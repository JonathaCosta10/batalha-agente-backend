"""Política operacional versionada (desafio_itau/politica/operacional-v1.json).

Equivalencia: os valores migrados das constantes são IGUAIS aos literais anteriores (antes de remover qualquer
literal, prova-se que o destino novo devolve o mesmo). Schema: prova negativa para tipo errado, campo
desconhecido, operador fora da lista e parâmetro inexistente. Limites: fronteira exata e arredondamento.
"""
import ast
import copy
import json
import unittest
from decimal import Decimal
from pathlib import Path

import conversas_apoio  # noqa: F401  (django.setup)

from desafio_itau import politica
from apps.conversas import interacao_dados as dd
from apps.conversas import projection
from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora import consultas, t3

RAIZ = Path(__file__).resolve().parents[1]


def linhas_divida(emp, juros, multas, n=1):
    return [{'emprestimos': emp, 'juros_pagos': juros, 'multas_atraso': multas} for _ in range(n)]


class Equivalencia(unittest.TestCase):
    """Literais que existiam no código em 2026-09-27 antes da migração."""

    def test_valores_iguais_aos_literais_anteriores(self):
        self.assertEqual(dd.LIMIAR_EQUILIBRIO_PCT, 1.0)
        self.assertEqual(dd.LIMIAR_DIVIDA_PCT_ENTRADAS, 10.0)
        self.assertEqual(dd.REFERENCIA_50_30_20, {'necessidades': 50, 'desejos': 30, 'futuro': 20})
        self.assertEqual(dd.INCLINACAO, {'meses_recentes': 3, 'variacao_min_pct': 15.0, 'diferenca_min_reais': 30.0,
                                         'media_min_reais': 50.0})
        self.assertEqual(t3.LIMIAR_SURPLUS, 0.15)
        self.assertEqual(repr(t3.LIMIAR_SURPLUS), '0.15')  # o SQL T3 usa repr(): texto renderizado idêntico
        self.assertEqual(politica.parametro('projecao.hipoteses_reducao', 'r_5'), Decimal('0.05'))
        self.assertEqual(politica.parametro('projecao.hipoteses_reducao', 'r_8'), Decimal('0.08'))

    def test_duplicacao_restante_em_consultas_bate_com_a_politica(self):
        # consultas.py replica o notebook (rótulos de cluster embutem "15%"); fica documentado e amarrado aqui.
        self.assertEqual(consultas.LIMIAR_SOBRA_SAUDAVEL_PCT, t3.LIMIAR_SURPLUS * 100)

    def test_projecao_da_os_mesmos_prazos(self):
        # Oráculo independente com os literais antigos 0.05/0.08: menor n inteiro com a*(1-r)^n <= b.
        def oraculo(a, b, r):
            n = 0
            while a * (1 - r) ** n > b:
                n += 1
            return n
        for a, b in (('600.00', '400.00'), ('1000.00', '600.00'), ('812.40', '300.00')):
            with self.subTest(a=a, b=b):
                esperado = {'status': 'projected', 'n_5': oraculo(Decimal(a), Decimal(b), Decimal('0.05')),
                            'n_8': oraculo(Decimal(a), Decimal(b), Decimal('0.08'))}
                self.assertEqual(projection.project(a, b), esperado)

    def test_cada_regra_aponta_origem_existente(self):
        for regra in politica.carregar().regras:
            for origem in regra.origem:
                with self.subTest(regra=regra.rule_id, arquivo=origem.arquivo):
                    self.assertTrue((RAIZ / origem.arquivo).exists())


class Schema(unittest.TestCase):
    def base(self):
        return json.loads(politica.ARQUIVO.read_text(encoding='utf-8'))

    def reprova(self, dados):
        with self.assertRaises(ValueError):
            politica.validar(dados)

    def test_arquivo_atual_valida(self):
        self.assertEqual(politica.validar(self.base()).versao, politica.versao())

    def test_prova_negativa_tipo_errado_e_campo_desconhecido(self):
        d = self.base()
        d['regras'][0]['parametros']['limiar_pct']['valor'] = 1.0  # float, não texto decimal
        self.reprova(d)
        d = self.base()
        d['regras'][0]['limiar_extra'] = '2'
        self.reprova(d)
        d = self.base()
        d['regras'][0]['parametros']['limiar_pct']['unidade'] = 'porcento'
        self.reprova(d)

    def test_prova_negativa_expressao_ou_operador_fora_da_lista(self):
        for operador in ('=>', 'in', "__import__('os').system('x')", 'lambda'):
            d = self.base()
            d['regras'][0]['condicao']['operador'] = operador
            with self.subTest(operador=operador):
                self.reprova(d)

    def test_prova_negativa_parametro_inexistente_e_id_duplicado(self):
        d = self.base()
        d['regras'][0]['condicao']['parametro'] = 'nao_existe'
        self.reprova(d)
        d = self.base()
        d['regras'].append(copy.deepcopy(d['regras'][0]))
        self.reprova(d)


def chamadas_proibidas(fonte):
    return [n.func.id for n in ast.walk(ast.parse(fonte))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ('eval', 'exec', 'compile')]


class SemEval(unittest.TestCase):
    """Guard por AST: o avaliador de condições não usa eval/exec/compile. Prova negativa com fonte sintética."""

    def test_prova_negativa(self):
        self.assertEqual(chamadas_proibidas("x = eval('1+1')"), ['eval'])

    def test_modulos_da_politica(self):
        for arquivo in (RAIZ / 'desafio_itau' / 'politica').glob('*.py'):
            with self.subTest(arquivo=arquivo.name):
                self.assertEqual(chamadas_proibidas(arquivo.read_text(encoding='utf-8')), [])


class Limites(unittest.TestCase):
    def test_divida_limite_exato_10(self):
        d = dd.resumir_divida(linhas_divida(700.0, 100.0, 0), 8000.0)  # 800/8000 = 10,00 %
        self.assertEqual((d['pct_da_entrada_media'], d['relevante']), (10.0, True))

    def test_divida_9_96_nao_arredonda_para_decidir(self):
        # 796,80/8000 = 9,96 %: exibido 10,0 (1 casa), mas a decisão usa o exato -> abaixo do limiar.
        d = dd.resumir_divida(linhas_divida(696.8, 100.0, 0), 8000.0)
        self.assertEqual((d['pct_da_entrada_media'], d['relevante']), (10.0, False))
        self.assertEqual(d['regra'], 'divida.relevante@1.0.0')

    def test_multa_sozinha_decide_mesmo_sem_renda(self):
        d = dd.resumir_divida(linhas_divida(0.0, 0.0, 1), 0.0)
        self.assertEqual((d['pct_da_entrada_media'], d['relevante']), (None, True))

    def test_sem_renda_e_sem_multa_nao_e_relevante_nem_zero(self):
        d = dd.resumir_divida(linhas_divida(500.0, 0.0, 0), None)
        self.assertIsNone(d['pct_da_entrada_media'])
        self.assertFalse(d['relevante'])

    def test_nulo_na_janela_nao_vira_zero(self):
        linhas = linhas_divida(100.0, 10.0, 0, n=2)
        linhas[1]['juros_pagos'] = None
        self.assertEqual(dd.resumir_divida(linhas, 8000.0)['estado'], dd.NAO_MEDIDO)

    def test_equilibrio_fronteira_estrita_1pct(self):
        self.assertEqual(dd.situacao_de(1000.0, 990.0), dd.SOBROU)        # |10| = 1 % -> não é < 1 %
        self.assertEqual(dd.situacao_de(1000.0, 990.01), dd.EQUILIBRIO)   # 0,999 %
        self.assertEqual(dd.situacao_de(1000.0, 1010.0), dd.FALTOU)

    def test_fluxo_sem_entradas_e_zero_e_nulo(self):
        self.assertEqual(dd.situacao_de(0.0, 150.0), dd.FALTOU)
        self.assertEqual(dd.situacao_de(0.0, 0.0), dd.NAO_MEDIDO)
        self.assertEqual(dd.situacao_de(None, 150.0), dd.NAO_MEDIDO)

    def test_kleene_indicador_ausente_nao_e_zero(self):
        self.assertIsNone(politica.avaliar('divida.relevante', {'divida_pct_entrada_media': None,
                                                                'multas_por_atraso_na_janela': 0}))
        self.assertTrue(politica.avaliar('divida.relevante', {'divida_pct_entrada_media': None,
                                                              'multas_por_atraso_na_janela': 2}))
        self.assertIsNone(politica.avaliar('t3.limiar_surplus', {}))
        self.assertTrue(politica.avaliar('t3.limiar_surplus', {'taxa_surplus_fracao': '0.15'}))
        self.assertFalse(politica.avaliar('t3.limiar_surplus', {'taxa_surplus_fracao': '0.1499'}))


if __name__ == '__main__':
    unittest.main()
