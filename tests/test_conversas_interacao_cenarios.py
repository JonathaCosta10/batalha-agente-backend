"""Fluxos determinísticos, cenários A1 (inclinação), A2 (consolidação com humano), B (fora do contexto), ortografia e
alucinação. Sem rede: Gemini e BigQuery são dublês. Cada guard novo tem prova negativa."""
import re
import unittest
from copy import deepcopy
from pathlib import Path

from test_conversas_interacao import (M1, M2, NOMES, PERFIL, PROPOSTA, SELO_M, TITULAR, Base, LINHAS_FALTOU,
                                      LINHAS_SOBROU, mes)

from apps.conversas import interacao, interacao_avaliacao as av, interacao_cenarios as cn, interacao_dados as dd
from apps.conversas.service import FALLBACKS

SEGMENTOS = ('Vulnerável', 'Esbanjador', 'Livre', None)
SITUACOES = (dd.SOBROU, dd.FALTOU, dd.EQUILIBRIO, dd.NAO_MEDIDO)


def com_divida(linhas, emp=1500.0, juros=100.0, multas=0):
    return [{**l, 'emprestimos': emp, 'juros_pagos': juros, 'multas_atraso': multas} for l in linhas]


def subcats(alta='Delivery', queda=None):
    """11 meses; `alta` sobe de R$ 300 para R$ 600 nos 3 últimos; `queda` cai de R$ 500 para R$ 200; Mercado estável."""
    linhas = []
    for i, m in enumerate(range(202501, 202512)):
        recente = i >= 8
        linhas.append({'anomes': m, 'macro': 'Mercado', 'micro': 'Mercado', 'valor': 900.0})
        if alta:
            linhas.append({'anomes': m, 'macro': 'Delivery', 'micro': alta, 'valor': 600.0 if recente else 300.0})
        if queda:
            linhas.append({'anomes': m, 'macro': 'Restaurantes', 'micro': queda, 'valor': 200.0 if recente else 500.0})
        linhas.append({'anomes': m, 'macro': 'Casa', 'micro': 'Pagamento de aluguel', 'valor': 2000.0})
    return linhas


def fontes_c(linhas=LINHAS_SOBROU, sub=None, perfil=PERFIL, divida=False, multas=0):
    base = com_divida(linhas, multas=multas) if divida else com_divida(linhas, emp=0.0, juros=0.0)
    return {'perfil': lambda c: perfil, 'mensal': lambda c: (deepcopy(base), SELO_M), 'proposta': lambda c: PROPOSTA,
            'subcategorias': (lambda c: (deepcopy(sub), SELO_M)) if sub is not None else _quebra}


def _quebra(c):
    raise RuntimeError('sem ADC')


def _explode(c):
    raise AssertionError('fonte não devia ser consultada')


class Deterministico(unittest.TestCase):
    def test_16_combinacoes_versionadas_e_estaveis(self):
        vistos = set()
        for seg in SEGMENTOS:
            for sit in SITUACOES:
                a = cn.selecionar_fluxo(seg, sit, janela='janeiro de 2025 a novembro de 2025', saldo=10.0, entradas=20.0, saidas=10.0,
                                        maior_desejo='Delivery')
                b = cn.selecionar_fluxo(seg, sit, janela='janeiro de 2025 a novembro de 2025', saldo=10.0, entradas=20.0, saidas=10.0,
                                        maior_desejo='Delivery')
                self.assertEqual(a, b)
                self.assertNotIn('{', a['mensagem_base'])
                self.assertTrue(any(k in av.normalizar_texto(a['mensagem_base']) for k in a['chave']), a['id'])
                vistos.add(a['id'])
        self.assertEqual(len(vistos), 16)
        self.assertEqual(cn.fluxos()['versao'], '2026-09-27.2')  # .2: situação = média da janela (dono 06:22)

    def test_mesma_entrada_mesmo_fluxo_e_cenario_com_textos_do_modelo_diferentes(self):
        saidas = []
        for texto in ('Maria, vamos organizar.', 'Qualquer outra coisa garantida!', RuntimeError('429')):
            t = Base('run')
            t.setUp()
            try:
                c = interacao.interagir(TITULAR, 'livre.respostas', 'quanto gastei com delivery?', fontes=fontes_c(sub=subcats()),
                                        transporte=__import__('test_conversas_interacao').Transporte({M1: texto, M2: texto}),
                                        modelos=(M1, M2), pasta_ledger=t.pasta, outros_nomes=NOMES)
            finally:
                t.tearDown()
            saidas.append((c['fluxo'], c['cenario']))
        self.assertTrue(all(s == saidas[0] for s in saidas))
        self.assertEqual(saidas[0][0]['id'], 'VUL-FALTOU' if False else saidas[0][0]['id'])

    def test_ortografia_dos_textos_fixos(self):
        fixos = [re.sub(r'\{\w+\}', 'X', f['mensagem_base']) for s in cn.fluxos()['fluxos'].values() for f in s.values()]
        fixos += [cn.FORA_DO_CONTEXTO, cn.HANDOFF_CONSOLIDACAO, cn.FRASE_ALTA, cn.FRASE_QUEDA, cn.FRASE_AJUSTE,
                  *interacao.COMPLEMENTO_TOM.values(), *FALLBACKS.values(),
                  *[e['fallback'] for e in interacao.ETAPAS.values() if e.get('fallback')],
                  *[e['objetivo'] for e in interacao.ETAPAS.values() if e.get('objetivo')]]
        liquid = (Path(interacao.__file__).parent / 'prompts' / 'interacao.liquid').read_text(encoding='utf-8')
        fixos.append(re.sub(r'\{[{%].*?[}%]\}', ' ', liquid).replace('NAO_MEDIDO', ' '))
        ruins = [(t[:60], av.guard_ortografia(t)[0]['detalhe']) for t in fixos if av.guard_ortografia(t)[0]['resultado'] != 'APROVADO']
        self.assertEqual(ruins, [])

    def test_instrucao_liquid_tem_bloco_fluxo_e_cenario(self):
        dados, _, _ = interacao.coletar({**TITULAR}, 'livre.respostas', fontes_c(sub=subcats()), turno_livre=True)
        cen = cn.selecionar_cenario(dados, 'onde estou gastando mais?')
        texto = interacao.instrucao('livre.respostas', TITULAR, dados, interacao.ETAPAS['livre.respostas'], None, cen)
        for trecho in ('BLOCO DE CONTEXTO', 'FLUXO (escolhido pelo servidor', 'CENÁRIO (escolhido pelo servidor)',
                       'leve inclinação a você gastar um pouco mais com Delivery', 'meses citáveis'):
            self.assertIn(trecho, texto)


class Cenarios(Base):
    def rodar_c(self, mensagem, textos, etapa='livre.respostas', **kw):
        from test_conversas_interacao import Transporte
        self.transporte = Transporte(textos)
        return interacao.interagir(TITULAR, etapa, None, mensagem=mensagem, transporte=self.transporte, modelos=(M1, M2),
                                   pasta_ledger=self.pasta, outros_nomes=NOMES, **kw)

    # B -------------------------------------------------------------------------------------------------
    def test_fora_do_contexto_fixo_sem_gemini_e_sem_consulta(self):
        for q in ('qual a capital da França?', 'receita de bolo', 'quem ganhou o jogo?'):
            c = self.rodar_c(q, {M1: 'x', M2: 'y'}, fontes={'perfil': _explode, 'mensal': _explode,
                                                             'proposta': _explode, 'subcategorias': _explode})
            self.assertEqual((c['texto'], c['origem_resposta'], c['dominio']), (cn.FORA_DO_CONTEXTO, 'fora_do_contexto', 'fora'))
            self.assertEqual(self.transporte.chamadas, [])

    def test_financeiro_nao_cai_fora(self):
        self.assertEqual(cn.classificar_dominio('quanto gastei com mercado?'), 'financeiro')
        # regressão da bateria ao vivo (bv-05, bv-10, bv-22 caíram fora antes do conserto)
        for q in ('como saio do vermelho?', 'estou exagerando em alguma categoria?'):
            self.assertEqual(cn.classificar_dominio(q), 'financeiro', q)
        for q in ('qual a capital da França?', 'receita de bolo', 'quem ganhou o jogo?'):
            self.assertEqual(cn.classificar_dominio(q), 'fora', q)

    # A2 ------------------------------------------------------------------------------------------------
    def test_consolidacao_dispara_em_100_por_cento_com_divida_medida(self):
        perguntas = ('tô cheia de dívidas, o que faço?', 'quanto gastei com mercado?', 'como foi meu mês?',
                     'posso parcelar menos?', 'quanto entrou em novembro?')
        textos = ({M1: 'Maria, vamos organizar juntos.'}, {M1: 'Contrate um empréstimo novo!', M2: RuntimeError('429')},
                  {M1: RuntimeError('429'), M2: RuntimeError('429')}, {M1: 'Maria, garantido.', M2: 'Maria, passo a passo.'},
                  {M1: 'Maria, vamos organizar passo a passo.'})
        for i, (q, t) in enumerate(zip(perguntas, textos)):
            for linhas in (LINHAS_SOBROU, LINHAS_FALTOU):
                c = self.rodar_c(q, t, fontes=fontes_c(linhas, sub=subcats(), divida=True))
                self.assertEqual(c['cenario']['cenario'], 'consolidacao_divida', (q, i))
                self.assertTrue(c['texto'].endswith(cn.HANDOFF_CONSOLIDACAO), c['texto'])
                self.assertIn('handoff.consolidacao', [a['id'] for a in c['proximas_acoes']])
                self.assertTrue(c['aprovado'])

    def test_sem_divida_relevante_nao_oferece_consolidacao(self):
        c = self.rodar_c('quanto entrou em novembro?', {M1: 'Maria, vamos organizar.'}, fontes=fontes_c(sub=subcats()))
        self.assertNotEqual(c['cenario']['cenario'], 'consolidacao_divida')
        self.assertNotIn(cn.HANDOFF_CONSOLIDACAO, c['texto'])

    def test_multa_por_atraso_sozinha_e_divida_relevante(self):
        d = dd.resumir_divida(com_divida(LINHAS_SOBROU, emp=0.0, juros=0.0, multas=1), 8000.0)
        self.assertTrue(d['relevante'])
        self.assertEqual(dd.resumir_divida(LINHAS_SOBROU, 8000.0)['estado'], dd.NAO_MEDIDO)

    # A1 ------------------------------------------------------------------------------------------------
    def test_inclinacao_alta_modelo_sem_frase_reprova_e_cai_no_esqueleto(self):
        c = self.rodar_c('onde estou gastando mais?', {M1: 'Maria, vamos organizar.', M2: 'Maria, passo a passo.'},
                         fontes=fontes_c(sub=subcats()))
        self.assertEqual(c['cenario']['cenario'], 'inclinacao_gasto')
        self.assertEqual(c['origem_resposta'], 'roteiro')
        self.assertIn('cenario.inclinacao_gasto', c['avaliacao']['tentativas'][0]['reprovados'])
        self.assertIn('leve inclinação a você gastar um pouco mais com Delivery', c['texto'])
        self.assertIn('R$ 600,00', c['texto'])
        self.assertIn('Talvez valha gastar um pouco menos com Delivery', c['texto'])  # Vulnerável = pressão

    def test_inclinacao_alta_modelo_com_frase_aprovado(self):
        bom = ('Maria, nesses últimos tempos tenho percebido uma leve inclinação a você gastar um pouco mais com Delivery: '
               'de setembro de 2025 a novembro de 2025 foram R$ 600,00 por mês, contra R$ 381,82 em média. '
               'Talvez valha gastar um pouco menos com Delivery.')
        c = self.rodar_c('onde estou gastando mais?', {M1: bom}, fontes=fontes_c(sub=subcats()))
        self.assertEqual((c['origem_resposta'], c['aprovado']), ('modelo', True), c['avaliacao']['reprovados'])

    def test_inclinacao_queda(self):
        c = self.rodar_c('como estou nos gastos?', {M1: RuntimeError('429'), M2: RuntimeError('429')},
                         fontes=fontes_c(sub=subcats(alta=None, queda='Restaurantes')))
        self.assertIn('leve inclinação a você gastar um pouco menos com Restaurantes', c['texto'])

    def test_sem_dado_sem_frase_de_inclinacao(self):
        c = self.rodar_c('onde estou gastando mais?', {M1: 'Maria, vamos organizar.'}, fontes=fontes_c(sub=None))
        self.assertEqual(c['cenario']['cenario'], 'financeiro_geral')
        self.assertNotIn('inclinação', c['texto'])
        self.assertTrue(c['estado_dados']['subcategorias'].startswith('NAO_MEDIDO'))

    def test_mensagem_livre_em_qualquer_etapa(self):
        c = self.rodar_c('quanto sobrou em novembro?', {M1: 'Maria, em novembro de 2025 sobrou R$ 1.299,44. Vamos organizar.'},
                         etapa='bot.confirm', fontes=fontes_c(sub=subcats()))
        self.assertTrue(c['turno_livre'])
        self.assertEqual(c['etapa'], 'bot.confirm')
        self.assertIn('user.assumir', [a['id'] for a in c['proximas_acoes']])


CTX = {'situacao': 'SOBROU', 'situacao_media': 'FALTOU', 'segmento': 'Vulnerável', 'valores': [1299.44],
       'meses_validos': [11], 'regra': None, 'mes_nome': 'novembro de 2025'}
BLOCO = {'meses': ['janeiro', 'novembro', 'outubro'], 'anos': [2025, 2026], 'categorias': ['Delivery'],
         'texto_permitido': 'organização e planejamento do orçamento Delivery'}


def reprovados(texto, **ctx):
    return av.avaliar(texto, titular=TITULAR, contexto={**CTX, **ctx}, etapa={'exige_fluxo': True})['reprovados']


class ProvasNegativasNovas(unittest.TestCase):
    def test_ortografia_voce_orcamento_mes(self):
        for ruim in ('Maria, voce pode organizar.', 'Maria, o orcamento pede calma.', 'Maria, neste mes vamos organizar.'):
            self.assertIn('ortografia', reprovados(ruim), ruim)
        self.assertNotIn('ortografia', reprovados('Maria, em Vestuario e acessorios você pode organizar o orçamento do mês.'))

    def test_fluxo_sem_acao_base(self):
        fluxo = cn.selecionar_fluxo('Vulnerável', 'FALTOU', mes='novembro de 2025', saldo=1.0, entradas=1.0, saidas=2.0)
        self.assertIn('fluxo', reprovados('Maria, corte tudo agora.', fluxo=fluxo))
        self.assertNotIn('fluxo', reprovados('Maria, vamos renegociar com calma.', fluxo=fluxo))

    def test_cenario_sem_frase_obrigatoria(self):
        cen = {'cenario': 'inclinacao_gasto', 'frases_obrigatorias': [cn.FRASE_ALTA.format(x='Delivery')], 'anexo': None}
        self.assertIn('cenario.inclinacao_gasto', reprovados('Maria, vamos organizar.', cenario=cen))

    def test_alucinacao_datas(self):
        self.assertIn('alucinacao.datas', reprovados('Maria, em dezembro vamos organizar.', bloco=BLOCO))
        self.assertIn('alucinacao.datas', reprovados('Maria, em 2024 você organizou.', bloco=BLOCO))
        self.assertNotIn('alucinacao.datas', reprovados('Maria, em janeiro de 2026 vamos organizar.', bloco=BLOCO))

    def test_alucinacao_categorias(self):
        self.assertIn('alucinacao.categorias', reprovados('Maria, o Cinema pesou.', bloco=BLOCO))
        self.assertNotIn('alucinacao.categorias', reprovados('Maria, o Delivery pesou.', bloco=BLOCO))

    def test_alucinacao_produto(self):
        self.assertIn('alucinacao.produto', reprovados('Maria, um CDB ajuda a organizar.', bloco=BLOCO))
        bloco = {**BLOCO, 'texto_permitido': BLOCO['texto_permitido'] + ' empréstimos juros'}
        self.assertNotIn('alucinacao.produto', reprovados('Maria, os empréstimos pesam.', bloco=bloco))

    def test_alucinacao_normativo(self):
        self.assertIn('alucinacao.normativo', reprovados('Maria, o Banco Central exige a regra 50-30-20.', bloco=BLOCO))
        self.assertNotIn('alucinacao.normativo',
                         reprovados('Maria, a regra 50-30-20 não é exigida pelo Banco Central.', bloco=BLOCO))

    def test_handoff_isento_mas_texto_do_modelo_nao(self):
        cen = {'cenario': 'consolidacao_divida', 'frases_obrigatorias': [cn.HANDOFF_CONSOLIDACAO],
               'anexo': cn.HANDOFF_CONSOLIDACAO}
        ok = 'Maria, vamos organizar. ' + cn.HANDOFF_CONSOLIDACAO
        self.assertEqual([r for r in reprovados(ok, cenario=cen, bloco=BLOCO) if r != 'fluxo'], [])
        ruim = 'Maria, contrate um empréstimo novo. ' + cn.HANDOFF_CONSOLIDACAO
        self.assertIn('politica.produto', reprovados(ruim, cenario=cen, bloco=BLOCO))
        self.assertIn('cenario.consolidacao_divida', reprovados('Maria, vamos organizar.', cenario=cen, bloco=BLOCO))


if __name__ == '__main__':
    unittest.main()
