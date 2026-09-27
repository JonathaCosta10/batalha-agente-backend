"""Deriva do catálogo de comunicação e integridade do corpus de avaliação da LLM (sem chamar o Gemini)."""
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import conversas_apoio  # noqa: F401 -- configura o Django como os demais testes

RAIZ = Path(__file__).resolve().parents[1]
COMUNICACAO = json.loads((RAIZ / 'desafio_itau' / 'politica' / 'comunicacao-v1.json').read_text(encoding='utf-8'))
CORPUS = json.loads((RAIZ / 'tests' / 'avaliacao' / 'corpus-llm-v1.json').read_text(encoding='utf-8'))


def constante(arquivo, nome):
    import importlib
    modulo = importlib.import_module(arquivo.removesuffix('.py').replace('/', '.'))
    if '[' in nome:
        base, chave = nome.split('[', 1)
        return getattr(modulo, base)[chave.strip("']")]
    return getattr(modulo, nome)


class DerivaComunicacao(unittest.TestCase):
    def test_bordao_existe_literalmente_na_origem(self):
        for b in COMUNICACAO['bordoes']:
            roteiro = json.loads((RAIZ / b['origem']['arquivo']).read_text(encoding='utf-8'))
            falas = {f['id']: f['texto'] for f in roteiro['falas']} if 'falas' in roteiro else None
            texto = falas[b['origem']['fala_id']] if falas else None
            if texto is None:  # roteiro sem chave 'falas': procura o id em qualquer lista de dicts
                texto = next(f['texto'] for v in roteiro.values() if isinstance(v, list)
                             for f in v if isinstance(f, dict) and f.get('id') == b['origem']['fala_id'])
            self.assertEqual(texto, b['texto'])
            self.assertEqual(b['aprovacao'], 'NAO_APROVADO')  # sem manual de marca, nada nasce aprovado

    def test_frases_fixas_apontam_para_constante_existente(self):
        for f in COMUNICACAO['frases_fixas']:
            valor = constante(f['origem']['arquivo'], f['origem']['constante'])
            self.assertTrue(valor, f['id'])

    def test_prova_negativa_constante_inexistente_reprova(self):
        with self.assertRaises((AttributeError, KeyError)):
            constante('apps/conversas/interacao_cenarios.py', 'NAO_EXISTE')

    def test_frases_fixas_nao_disparam_o_lexico(self):
        from desafio_itau.politica import lexico
        for f in COMUNICACAO['frases_fixas']:
            valor = constante(f['origem']['arquivo'], f['origem']['constante'])
            textos = valor.values() if isinstance(valor, dict) else [valor]
            for t in textos:
                t = t if isinstance(t, str) else json.dumps(t, ensure_ascii=False)
                self.assertEqual(lexico.bloqueios(t), [], f['id'])


class Corpus(unittest.TestCase):
    ESTADOS = {'ENCAMINHAMENTO', 'RECUSA_SEGURA', 'ESCLARECIMENTO', 'IDENTIFICACAO', 'DADOS_INSUFICIENTES',
               'EDUCACAO_GERAL', 'ANALISE_DESCRITIVA', 'SIMULACAO', 'INDISPONIVEL'}

    def test_trinta_casos_unicos_com_estados_validos(self):
        casos = CORPUS['casos']
        self.assertGreaterEqual(len(casos), 30)
        self.assertEqual(len({c['id'] for c in casos}), len(casos))
        self.assertEqual(CORPUS['repeticoes_por_caso'], 5)
        for c in casos:
            self.assertTrue(set(c['estados_aceitos']) <= self.ESTADOS, c['id'])
            self.assertIn(c['fonte'], ('MEDIDO', 'NAO_MEDIDO'))

    def test_estados_do_corpus_existem_na_politica(self):
        from desafio_itau import politica
        self.assertTrue(self.ESTADOS - {'INDISPONIVEL'} <= set(politica.estados()) | {'INDISPONIVEL'})

    def test_runner_sem_real_nao_chama_nada_e_diz_nao_executado(self):
        import sys
        sys.path.insert(0, str(RAIZ / 'scripts'))
        import avaliar_llm
        saida = io.StringIO()
        with redirect_stdout(saida):
            codigo = avaliar_llm.main([])
        self.assertEqual(codigo, 2)
        r = json.loads(saida.getvalue())
        self.assertEqual(r['estado'], 'NAO_EXECUTADO')
        self.assertEqual(r['plano']['casos'] * r['plano']['repeticoes'], 150)

    def test_resumo_calcula_metricas_com_denominadores(self):
        import sys
        sys.path.insert(0, str(RAIZ / 'scripts'))
        import avaliar_llm
        casos = [{'id': 'a', 'espera_liberacao': True}]
        linhas = [{'caso': 'a', 'http': 200, 'latencia_ms': 10, 'schema_ok': True, 'violacoes': [], 'tokens': 5},
                  {'caso': 'a', 'http': 503, 'latencia_ms': 30, 'schema_ok': True, 'violacoes': [], 'tokens': 0}]
        r = avaliar_llm.resumo(linhas, casos)
        self.assertEqual((r['execucoes'], r['liberadas'], r['taxa_de_fallback'], r['falso_bloqueio']), (2, 1, 0.5, 0.5))


if __name__ == '__main__':
    unittest.main()
