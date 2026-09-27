"""Regressão offline dos classificadores determinísticos de intenção sobre um corpus gerado pelo Gemini. Sem rede.

Corpus: datasets/corpus-intencao-gemini-2026-09-27T0857.jsonl (60 frases, 12 por rótulo, gemini-3.5-flash-lite,
gerado por scripts/gemini_trabalho_pesado.py). Medição de 2026-09-27 08:57 BRT em
relatorios/gemini-deterministico/2026-09-27T0857.json. O PISO de acerto por rótulo é o medido nesse dia,
arredondado para baixo: o classificador pode melhorar, nunca piorar.
CONHECIDAS_ERRADAS alimenta a tarefa F3 (taxonomia de intenção): frases que hoje erram, com o rótulo esperado.
"""
import importlib.util
import json
import re
import unittest
from pathlib import Path

import conversas_apoio  # noqa: F401  (faz django.setup)

RAIZ = Path(__file__).resolve().parents[1]
CORPUS = RAIZ / 'datasets' / 'corpus-intencao-gemini-2026-09-27T0857.jsonl'

_spec = importlib.util.spec_from_file_location('gemini_trabalho_pesado', RAIZ / 'scripts' / 'gemini_trabalho_pesado.py')
gtp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gtp)

# Medido 2026-09-27 08:57 BRT: acertos/total -> 10/12, 10/12, 10/12, 12/12, 3/12.
# Extremo 7/12 (58,3%) medido 2026-09-27 09:40 BRT, depois do léxico novo da f7 (desafio_itau/politica/),
# com gtp.medir sobre este corpus; os outros rótulos seguiram iguais (10/12, 10/12, 10/12, 12/12).
# Piso de extremo 25 -> 58: Decisão D-6, 2026-09-27 (dono autorizou).
PISO_PCT = {'inclinacao_gasto': 83, 'consolidacao_divida': 83, 'financeiro_geral': 83, 'fora_do_contexto': 100,
            'extremo': 58}

CONHECIDAS_ERRADAS = {
    'estou sem controle nenhum com cartao': 'inclinacao_gasto',          # previsto financeiro_geral
    'como fzr p parar de comprar por impulsao?': 'inclinacao_gasto',     # previsto fora_do_contexto
    'qual a melhor forma de limpar meu nome?': 'consolidacao_divida',    # previsto fora_do_contexto
    'quero unificar meus debitos': 'consolidacao_divida',                # previsto fora_do_contexto
    'quanto tenho guardado?': 'financeiro_geral',                        # previsto fora_do_contexto
    'quero planejar meu proximo mes': 'financeiro_geral',                # previsto fora_do_contexto
    # Saíram (D-6, acertam com o léxico da f7, medido 09:40 BRT): 'vc e mto linda sabia?', 'casaria facil com voce',
    # 'odeio esse banco e odeio voce', 'as coisas tao tao pesadas q as vezes da vontade de sumir'.
    'queria q vc fosse de verdade rs': 'extremo',                        # previsto fora_do_contexto
    'nao aguento mais essa pressao toda na minha cabeca': 'extremo',
    'sua voz e irritante': 'extremo',
    'tô cansado de lutar contra tudo isso sozinho': 'extremo',
    'voce e o robo mais simpatica q ja vi': 'extremo',
}


def linhas():
    return [json.loads(l) for l in CORPUS.read_text(encoding='utf-8').splitlines() if l.strip()]


class Selo(unittest.TestCase):
    def test_cada_linha_tem_modelo_hora_e_sha(self):
        ls = linhas()
        self.assertEqual(len(ls), 60)
        for l in ls:
            self.assertTrue(l['modelo'].startswith('gemini-'), l['id'])
            self.assertTrue(l['model_version'], l['id'])
            self.assertRegex(l['gerado_em'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-03:00$')
            self.assertRegex(l['prompt_sha256'], r'^[0-9a-f]{64}$')
            self.assertIn(l['rotulo_esperado'], gtp.ROTULOS)
            self.assertTrue(l['texto'].strip())

    def test_nome_do_arquivo_bate_com_a_hora_do_selo(self):
        hora = re.search(r'(\d{4}-\d{2}-\d{2}T\d{4})', CORPUS.name).group(1)
        self.assertTrue(all(l['gerado_em'][:16].replace(':', '') == hora for l in linhas()))


class Piso(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = gtp.medir(linhas())

    def test_acerto_por_rotulo_nao_cai_abaixo_do_medido(self):
        for rotulo, piso in PISO_PCT.items():
            with self.subTest(rotulo=rotulo):
                self.assertGreaterEqual(self.m['acerto_por_rotulo'][rotulo]['pct'], piso)

    def test_nenhum_erro_novo_fora_das_conhecidas(self):
        novos = [(e['texto'], e['esperado'], e['previsto']) for e in self.m['erradas']
                 if CONHECIDAS_ERRADAS.get(e['texto']) != e['esperado']]
        self.assertEqual(novos, [])

    def test_prova_negativa_piso_reprova_classificador_ruim(self):
        # Um classificador que manda tudo para 'fora' TEM de ficar abaixo do piso em pelo menos um rótulo.
        original = gtp.classificar
        gtp.classificar = lambda t: ('fora_do_contexto', {'extremo': None, 'dominio': 'fora', 'intencao_gasto': False})
        try:
            ruim = gtp.medir(linhas())
        finally:
            gtp.classificar = original
        self.assertTrue(any(ruim['acerto_por_rotulo'][r]['pct'] < p for r, p in PISO_PCT.items()))


if __name__ == '__main__':
    unittest.main()
