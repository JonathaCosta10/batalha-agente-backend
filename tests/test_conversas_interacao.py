"""POST conversas/interacao/: dados medidos -> Gemini -> guards em tempo de execução -> ledger. Sem rede.

Gemini e BigQuery são dublês (transporte falso e fontes falsas). Cada guard tem prova negativa: um texto ruim
sintético que ele TEM de reprovar (classe ProvasNegativas).
"""
import json
import shutil
import tempfile
import unittest
from copy import deepcopy
from unittest import mock

from conversas_apoio import MARIA, PERFIL, SELO  # noqa: F401  (faz django.setup)

from django.test import Client  # noqa: E402

from apps.conversas import interacao, interacao_avaliacao as av, interacao_dados as dd  # noqa: E402
from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora import t3  # noqa: E402
from apps.context_agent_datadriven.services import perfil_usuario  # noqa: E402

TITULAR = {'codigo': MARIA, 'pessoa': 'Maria', 'genero': 'F', 'indice': 1}
NOMES = ['Maria', 'Eduardo', 'Ana']


def mes(anomes, e, s, n=6000.0, d=1000.0, f=10.0, x=1500.0):
    return {'anomes': anomes, 'entradas': e, 'saidas': s, 'necessidades': n, 'desejos': d,
            'futuro_programado': f, 'fora_da_regra': x, 'saidas_sem_classe': 0}


# Regra do dono (06:22): a situação é a da MÉDIA da janela. LINHAS_SOBROU: média SOBROU (+R$ 1.518,23/mês) com o
# mês mais recente FALTOU, para provar que o mês isolado não decide.
LINHAS_SOBROU = [mes(202500 + m, 9800.0, 8000.0) for m in range(1, 11)] + [mes(202511, 8596.41, 9895.85)]
LINHAS_FALTOU = [mes(202500 + m, 4000.0, 8000.0) for m in range(1, 11)] + [mes(202511, 5938.93, 7106.68)]
SELO_M = {**SELO, 'jobs': {'mensal_50_30_20': 'job-teste'}, 'data_corte': '2025-12-22'}
PROPOSTA = {'estado': 'CORTE_INSUFICIENTE', 'regra': 'corte_seguro_ate_surplus_15',
            'compromissos': [{'subcategoria': 'Delivery', 'categoria_macro': 'Delivery', 'gasto_atual': 913.82,
                              'corte': 913.82, 'meta': 0.0, 'texto': 'Pausar Delivery em janeiro (economia de R$ 913,82).'}],
            'totais': {'valor_liberado': 913.82, 'reserva': 0.0, 'falta_apos_cortes': 3274.48, 'necessario_para_surplus_15': 4188.3},
            'selos': {'subcategorias': SELO}}


def fontes(linhas=LINHAS_SOBROU, perfil=PERFIL):
    return {'perfil': lambda c: perfil, 'mensal': lambda c: (deepcopy(linhas), SELO_M), 'proposta': lambda c: PROPOSTA}


def quebrada(c):
    raise RuntimeError('sem ADC')


FONTES_QUEBRADAS = {'perfil': quebrada, 'mensal': quebrada, 'proposta': quebrada}


class Transporte:
    """Dublê do POST generateContent: um texto por modelo; guard de entrada devolve `decisao`."""

    def __init__(self, textos, decisao='allow'):
        self.textos, self.decisao, self.chamadas = textos, decisao, []

    def __call__(self, modelo, corpo):
        self.chamadas.append(modelo)
        props = corpo['generationConfig']['responseJsonSchema'].get('properties', {})
        if 'decision' in props:
            out = {'decision': self.decisao, 'reason_codes': [], 'constraints': [], 'policy_version': '1.0'}
        else:
            texto = self.textos.get(modelo)
            if isinstance(texto, Exception):
                raise texto
            out = {'texto': texto}
        return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(out, ensure_ascii=False)}]}}],
                'usageMetadata': {'promptTokenCount': 900, 'candidatesTokenCount': 60, 'totalTokenCount': 960},
                'modelVersion': f'{modelo}-fake'}


M1, M2 = 'gemini-flash-latest', 'gemini-3.5-flash-lite'
JANELA = 'janeiro de 2025 a novembro de 2025'
BOM_SOBROU = (f'Maria, na média mensal de {JANELA} sobrou R$ 1.518,23 por mês: entraram R$ 9.690,58 e saíram '
              'R$ 8.172,35. Vamos organizar o próximo passo.')


class Base(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)

    def rodar(self, etapa, textos, escolha=None, linhas=LINHAS_SOBROU, f=None, decisao='allow', **kw):
        self.transporte = Transporte(textos, decisao)
        return interacao.interagir(TITULAR, etapa, escolha, fontes=f or fontes(linhas), transporte=self.transporte,
                                   modelos=(M1, M2), pasta_ledger=self.pasta, outros_nomes=NOMES, **kw)

    def ledger(self):
        import pathlib
        return [json.loads(l) for a in pathlib.Path(self.pasta).glob('*.jsonl') for l in a.read_text(encoding='utf-8').splitlines()]


class Fluxo(Base):
    def test_sobrou_aprovado_com_medidas_de_execucao(self):
        c = self.rodar('intro.carrossel.1', {M1: BOM_SOBROU})
        self.assertEqual((c['situacao'], c['situacao_media'], c['origem_resposta'], c['aprovado']), ('SOBROU', 'SOBROU', 'modelo', True))
        self.assertEqual(c['situacao_mes_recente'], 'FALTOU')  # informativo: não decide
        self.assertEqual(c['ancora_temporal']['janela'], JANELA)
        a = c['avaliacao']
        self.assertEqual((a['modelo'], a['model_version'], a['tokens']['total']), (M1, M1 + '-fake', 960))
        self.assertIsInstance(a['latencia_ms'], int)
        self.assertEqual(c['selo']['mensal']['jobs'], {'mensal_50_30_20': 'job-teste'})
        self.assertEqual([x['id'] for x in c['proximas_acoes']], ['intro.gatilho_agora'])
        self.assertTrue(any(r['id'].startswith('RC-08-2023:art-2') for r in c['regras_aplicadas']))
        [linha] = self.ledger()
        self.assertEqual((linha['id_usuario_sha256_12'], linha['aprovado'], linha['modelo']), (av.sha(MARIA)[:12], True, M1))
        self.assertNotIn('indice', linha)  # índice posicional não vai ao ledger
        self.assertNotIn(MARIA, json.dumps(linha))
        self.assertNotIn('texto', linha)

    def test_reprovado_no_primeiro_modelo_passa_ao_segundo(self):
        ruim = f'Maria, na média mensal de {JANELA} faltou R$ 1.518,23 por mês. Vamos organizar.'
        c = self.rodar('intro.carrossel.1', {M1: ruim, M2: BOM_SOBROU})
        self.assertEqual((c['avaliacao']['modelo'], c['origem_resposta']), (M2, 'modelo'))
        t1, t2 = c['avaliacao']['tentativas']
        self.assertEqual((t1['aprovado'], t1['reprovados'], t2['aprovado']), (False, ['coerencia.sentido', 'situacao'], True))
        self.assertEqual(self.ledger()[0]['tentativas'][0]['reprovados'], ['coerencia.sentido', 'situacao'])

    def test_nenhum_modelo_passa_serve_roteiro_rotulado(self):
        c = self.rodar('intro.carrossel.1', {M1: 'Tudo garantido, Maria.', M2: RuntimeError('HTTP 503')})
        self.assertEqual((c['origem_resposta'], c['aprovado'], c['avaliacao']['modelo']), ('roteiro', True, None))
        self.assertIn('sobrou R$ 1.518,23 por mês', c['texto'])
        self.assertEqual(c['avaliacao']['tentativas'][1]['erro'], 'RuntimeError')

    def test_faltou_roteiro_diz_faltou(self):
        c = self.rodar('intro.carrossel.1', {M1: RuntimeError('x'), M2: RuntimeError('x')}, linhas=LINHAS_FALTOU)
        self.assertEqual((c['situacao'], c['origem_resposta']), ('FALTOU', 'roteiro'))
        self.assertIn('faltou R$ 3.742,52 por mês', c['texto'])
        self.assertEqual(c['situacao_mes_recente'], 'FALTOU')

    def test_roteiro_que_tambem_reprova_vira_503(self):
        with mock.patch.object(interacao, 'texto_roteiro', return_value='Maria, sobrou R$ 9.999,00!'):
            with self.assertRaises(interacao.SemResposta) as erro:
                self.rodar('intro.carrossel.1', {M1: 'x', M2: 'y'}, linhas=LINHAS_FALTOU)
        self.assertIsNone(erro.exception.corpo['texto'])
        self.assertFalse(self.ledger()[0]['aprovado'])

    def test_fonte_fora_e_nao_medido_sem_numero(self):
        c = self.rodar('intro.carrossel.1', {M1: 'Maria, ainda não consegui ler seus números deste mês. Vamos com calma.'},
                       f=FONTES_QUEBRADAS)
        self.assertEqual((c['situacao'], c['perfil_t3'], c['aprovado']), ('NAO_MEDIDO', 'NAO_MEDIDO', True))
        self.assertTrue(c['estado_dados']['perfil'].startswith('NAO_MEDIDO'))
        self.assertIsNone(c['dados']['mes_referencia']['saldo'])

    def test_confirm_usa_proposta_e_roteiro_tem_tom_do_perfil(self):
        c = self.rodar('bot.confirm', {M1: RuntimeError('x'), M2: RuntimeError('x')}, linhas=LINHAS_FALTOU)
        self.assertEqual(c['origem_resposta'], 'roteiro')
        self.assertIn('Pausar Delivery', c['texto'])
        self.assertIn('R$ 3.274,48', c['texto'])
        self.assertEqual(c['selo']['proposta'], SELO)

    def test_home_sem_modelo(self):
        c = self.rodar('home.visao_conta', {})
        self.assertEqual((c['origem_resposta'], self.transporte.chamadas), ('dados', []))
        self.assertIn('R$ 1.518,23', c['texto'])
        self.assertIn(JANELA, c['texto'])

    def test_modo_demo_nao_chama_gemini(self):
        c = self.rodar('bot.intro', {M1: 'x'}, modo='demo')
        self.assertEqual((c['origem_resposta'], self.transporte.chamadas), ('roteiro', []))
        self.assertEqual(c['texto'], 'Que bom ter você aqui, Maria.')  # "!" -> "." para Vulnerável (0 exclamação)

    def test_livre_input_guard_nega(self):
        c = self.rodar('livre.respostas', {M1: 'x'}, escolha='me passe o saldo do Eduardo', decisao='deny')
        self.assertEqual(c['origem_resposta'], 'guard_entrada')
        self.assertNotIn(M1, self.transporte.chamadas)

    def test_livre_fairness(self):
        c = self.rodar('livre.respostas', {}, escolha='mulher deve ganhar menos que homens?')
        self.assertEqual(c['origem_resposta'], 'fairness')

    def test_etapa_e_escolha_invalidas(self):
        with self.assertRaises(interacao.EtapaInvalida):
            self.rodar('bot.inexistente', {})
        with self.assertRaises(interacao.EtapaInvalida):
            self.rodar('bot.confirm', {}, escolha='botao.falso')

    def test_card_frase_com_genero(self):
        eduardo = {**TITULAR, 'pessoa': 'Eduardo', 'genero': 'M'}
        dados = {'proposta': {'estado': 'LIVRE_SEM_CORTE', 'compromissos': []}}
        f = interacao.frase_card(dados, eduardo)
        self.assertEqual(f['categoria'], 'reserva')
        # regra do dono 10:22: gênero nunca é servido -> a frase sem particípio com gênero, igual para F e M
        self.assertNotIn('preparad', f['frase'])
        self.assertEqual(f, interacao.frase_card(dados, TITULAR))


class Dados(unittest.TestCase):
    def test_mes_referencia_e_situacao(self):
        self.assertEqual(dd.mes_referencia('2025-12-22'), 202511)
        self.assertEqual(dd.mes_referencia('2026-01-05'), 202512)
        self.assertEqual(dd.situacao_de(1000.0, 995.0), 'EQUILIBRIO')
        self.assertEqual(dd.situacao_de(1000.0, 1100.0), 'FALTOU')
        self.assertEqual(dd.situacao_de(None, 10.0), 'NAO_MEDIDO')

    def test_sem_mes_de_referencia_e_nao_medido_nao_zero(self):
        r = dd.resumir_mensal(LINHAS_SOBROU[:-1], '2025-12-22')
        self.assertEqual((r['mes_referencia']['situacao'], r['mes_referencia']['saldo']), ('NAO_MEDIDO', None))

    def test_50_30_20_e_projecao(self):
        linhas = [mes(202500 + m, 10000.0, 9000.0, n=5000.0, d=3000.0, f=0.0, x=1000.0) for m in range(1, 12)]
        r = dd.resumir_mensal(linhas, '2025-12-22')
        g = r['regra_50_30_20']
        self.assertEqual((g['necessidades']['pct'], g['desejos']['pct'], g['futuro']['pct']), (50.0, 30.0, 10.0))
        self.assertEqual(r['projecao']['lacuna_mensal_para_20'], 1000.0)
        self.assertEqual(r['projecao']['status'], 'projected')
        self.assertGreater(r['projecao']['meses_8'], 0)

    def test_mapa_cobre_todas_as_macros_do_t3(self):
        self.assertEqual({m for m, _ in dd.CLASSE_50_30_20}, set(t3.MAPA_GRUPOS))
        self.assertTrue(set(dd.CLASSE_50_30_20.values()) <= {dd.NECESSIDADES, dd.DESEJOS, dd.FUTURO, dd.FORA})
        self.assertIn("'Delivery' AS micro", dd.montar_sql())


CTX = {'situacao': 'SOBROU', 'situacao_media': 'FALTOU', 'segmento': 'Vulnerável',
       'valores': [9895.85, 8596.41, 1299.44, -1729.62, 86.6, 12.8], 'meses_validos': [11],
       'regra': {'necessidades': {'pct': 86.6}, 'desejos': {'pct': 12.8}, 'futuro': {'pct': 0.1}},
       'mes_nome': 'novembro de 2025'}


def reprovados(texto, etapa=None, ctx=CTX):
    return av.avaliar(texto, titular=TITULAR, contexto=ctx, etapa=etapa or {}, outros_nomes=NOMES)['reprovados']


class ProvasNegativas(unittest.TestCase):
    """Cada guard reprova o seu caso ruim sintético, e aprova o caso bom correspondente."""

    def test_numeros(self):
        self.assertIn('numeros', reprovados('Em novembro sobrou R$ 2.000,00. Vamos organizar.'))
        self.assertIn('numeros', reprovados('Você chega lá em 7 meses. Vamos organizar.'))
        self.assertNotIn('numeros', reprovados('Em novembro sobrou R$ 1.299,44 em 11 meses de dados. Vamos organizar.'))

    def test_situacao_contraria(self):
        self.assertIn('situacao', reprovados('Em novembro faltou dinheiro. Vamos organizar.'))
        self.assertIn('situacao', reprovados('Em novembro ficou no vermelho. Vamos organizar.'))

    def test_situacao_media_vale_so_na_frase_da_media(self):
        # Até 06:22 este texto passava (mês SOBROU, média FALTOU). Regra do dono: sentido único -> reprova.
        self.assertIn('coerencia.sentido',
                      reprovados('Em novembro sobrou R$ 1.299,44. Em média, faltou R$ 1.729,62. Vamos organizar.'))
        self.assertIn('situacao', reprovados('Em média sobrou dinheiro. Vamos organizar.'))

    def test_coerencia_sobrou_com_faltam_reais_reprova(self):
        # prova negativa pedida (conflito medido pelo front às 06:53): bot.confirm dizendo SOBROU e "faltam R$"
        confirm = interacao.ETAPAS['bot.confirm']
        ctx_f = {**CTX, 'situacao': 'FALTOU', 'situacao_media': 'FALTOU', 'valores': CTX['valores'] + [3274.48]}
        ctx_s = {**CTX, 'situacao_media': 'SOBROU', 'valores': CTX['valores'] + [3274.48]}
        ruim = 'Em média SOBROU R$ 1.299,44 por mês. Ainda faltam R$ 3.274,48 por mês; vamos organizar.'
        self.assertIn('coerencia.sentido', reprovados(ruim, confirm, ctx_s))
        self.assertIn('coerencia.sentido', reprovados(ruim, confirm, ctx_f))
        self.assertIn('coerencia.sentido', reprovados('Em média sobrou dinheiro por mês. Vamos organizar.', None, ctx_f))
        bom = 'Ainda faltam R$ 3.274,48 por mês; o próximo passo é renegociar e organizar os compromissos.'
        self.assertNotIn('coerencia.sentido', reprovados(bom, confirm, ctx_f))

    def test_periodo_uma_so_ancora(self):
        bloco = {'meses': ['janeiro', 'fevereiro', 'marco', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro',
                           'outubro', 'novembro', 'dezembro'], 'anos': [2025, 2026], 'categorias': [], 'texto_permitido': '',
                 'periodos_permitidos': [JANELA, 'janeiro a novembro de 2025', '22 de dezembro de 2025', 'janeiro de 2026']}
        ctx = {**CTX, 'situacao_media': 'SOBROU', 'bloco': bloco}
        self.assertIn('alucinacao.periodo', reprovados('Em novembro de 2025 sobrou R$ 1.299,44. Vamos organizar.', None, ctx))
        self.assertIn('alucinacao.periodo', reprovados('Em média, de março a junho, vamos organizar.', None, ctx))
        self.assertNotIn('alucinacao.periodo', reprovados(
            f'Em média, de {JANELA}, sobrou R$ 1.299,44 por mês. Os compromissos de janeiro de 2026 ajudam a organizar.',
            None, ctx))
        self.assertNotIn('alucinacao.periodo', reprovados('Seus compromissos de janeiro estão organizados.', None, ctx))

    def test_situacao_da_conversa_e_a_media(self):
        r = dd.resumir_mensal(LINHAS_SOBROU, '2025-12-22')
        self.assertEqual((r['mes_referencia']['situacao'], r['situacao_conversa']['situacao']), ('FALTOU', 'SOBROU'))
        self.assertEqual((r['situacao_conversa']['janela'], r['situacao_conversa']['registros_ate']), (JANELA, '22/12/2025'))
        self.assertEqual(dd.situacao_da_conversa({}), 'NAO_MEDIDO')
        self.assertEqual(dd.resumir_mensal([], '2025-12-22')['situacao_conversa']['situacao'], 'NAO_MEDIDO')

    def test_situacao_exigida_e_nao_medido(self):
        self.assertIn('situacao', reprovados('Vamos organizar seu mês.', {'exige_situacao': True}))
        nm = {**CTX, 'situacao': 'NAO_MEDIDO', 'situacao_media': None, 'valores': []}
        self.assertIn('situacao', reprovados('Este mês sobrou dinheiro. Vamos organizar.', {'exige_situacao': True}, nm))

    def test_nome(self):
        self.assertIn('nome.presente', reprovados('Que bom ter você aqui.', {'exige_nome': True}))
        self.assertIn('nome.alheio', reprovados('Que bom ter você aqui, Eduardo.', {'exige_nome': True}))
        self.assertIn('nome.genero', reprovados('Maria, você está preparado para organizar?'))
        # gênero nunca é servido (dono 10:22): também a forma "certa" para F reprova
        self.assertIn('nome.genero', reprovados('Maria, você está preparada para organizar?'))
        self.assertNotIn('nome.genero', reprovados('Maria, você pode organizar agora? Seu plano está pronto.'))

    def test_politica(self):
        self.assertIn('politica.promessa', reprovados('Com esse plano o resultado é garantido. Vamos organizar.'))
        self.assertIn('politica.produto', reprovados('Contrate um empréstimo consignado para organizar.'))
        self.assertIn('politica.produto', reprovados('Vamos organizar: invista na poupança o que sobrar.'))
        self.assertIn('politica.safe_text', reprovados('Vamos organizar com juros de 2% ao mês.'))
        self.assertIn('politica.tom.exclamacoes', reprovados('Vamos organizar!'))  # Vulnerável: 0 exclamação
        self.assertEqual(reprovados('Vamos organizar os compromissos com calma.'), [])

    def test_50_30_20(self):
        self.assertIn('regra_50_30_20.necessidades', reprovados('Suas necessidades ocupam 50% da renda. Vamos organizar.'))
        self.assertIn('regra_50_30_20.desejos', reprovados('Seus desejos ocupam 86,6% da renda. Vamos organizar.'))
        self.assertEqual(reprovados('Suas necessidades ocupam 86,6% da renda; a regra sugere até 50%. Vamos organizar.'), [])

    def test_50_30_20_periodo(self):
        # caso real do smoke de 2026-09-27 (m04): a média jan-nov foi atribuída a novembro
        self.assertIn('regra_50_30_20.periodo',
                      reprovados('Em novembro de 2025 suas necessidades estão em 86,6%. Vamos organizar.'))
        self.assertEqual(reprovados('Em média, suas necessidades estão em 86,6% da renda. Vamos organizar.'), [])

    def test_ortografia(self):
        # caso real do smoke (m02, m08, m09): "Ola Maria", "voce", "estao"
        self.assertIn('ortografia', reprovados('Ola Maria, voce pode seguir. Vamos organizar.'))
        self.assertNotIn('ortografia', reprovados('Olá Maria, você pode seguir. Vamos organizar.'))

    def test_tom_exigido_so_nas_etapas_de_acao(self):
        self.assertIn('tom_t3.exigidos', reprovados('Seu mês terminou.', {'exige_tom': True}))
        self.assertNotIn('tom_t3.exigidos', reprovados('Seu mês terminou.', {'exige_tom': False}))

    def test_ledger_recusa_uuid_e_texto(self):
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(ValueError):
                av.registrar({'etapa': 'x', 'id': MARIA}, pasta)
            with self.assertRaises(ValueError):
                av.registrar({'etapa': 'x', 'texto': 'Maria'}, pasta)


class Resumo(unittest.TestCase):
    def test_vazio_e_nao_medido(self):
        with tempfile.TemporaryDirectory() as pasta:
            r = av.resumo(pasta)
        self.assertEqual((r['respostas'], r['taxa_aprovacao_respostas'], r['latencia_ms']), (0, 'NAO_MEDIDO', 'NAO_MEDIDO'))

    def test_taxa_p50_p95_por_guard(self):
        with tempfile.TemporaryDirectory() as pasta:
            for lat, ok in ((100, True), (200, True), (300, False), (1000, True)):
                av.registrar({'etapa': 'bot.intro', 'origem_resposta': 'modelo' if ok else 'roteiro', 'aprovado': True,
                              'tentativas': [{'modelo': M1, 'aprovado': ok, 'latencia_ms': lat,
                                              'reprovados': [] if ok else ['situacao']}]}, pasta)
            r = av.resumo(pasta)
        self.assertEqual((r['respostas'], r['taxa_aprovacao_tentativas'], r['reprovacoes_por_guard']), (4, 0.75, {'situacao': 1}))
        self.assertEqual((r['latencia_ms']['p50'], r['latencia_ms']['p95']), (250.0, 895.0))


class Http(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.c = Client()
        self.sid = perfil_usuario.definir_usuario(MARIA)['sessao_id']
        self.trans = Transporte({M1: BOM_SOBROU})
        self.patches = [mock.patch.dict(interacao.FONTES, fontes()),
                        mock.patch.object(interacao, 'gateway_para',
                                          lambda m, t=None, b=300: interacao.GatewayInteracao(model=m, transporte=self.trans)),
                        mock.patch.object(av, 'PASTA_LEDGER', __import__('pathlib').Path(self.pasta))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.pasta, ignore_errors=True)

    def post(self, corpo, **headers):
        return self.c.post('/api/v1/context-agent/conversas/interacao/', data=json.dumps(corpo),
                           content_type='application/json', **headers)

    def test_ok(self):
        r = self.post({'etapa': 'intro.carrossel.1', 'escolha': 'intro.gatilho_agora'}, HTTP_X_SESSAO_ID=self.sid)
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual((r.json()['situacao'], r.json()['origem_resposta']), ('SOBROU', 'modelo'))
        resumo = self.c.get('/api/v1/context-agent/conversas/avaliacoes/resumo/').json()
        self.assertEqual(resumo['respostas'], 1)

    def test_sem_header_sessao_invalida_e_schema(self):
        self.assertEqual(self.post({'etapa': 'bot.intro'}).status_code, 401)
        self.assertEqual(self.post({'etapa': 'bot.intro'}, HTTP_X_SESSAO_ID='nao-existe').status_code, 404)
        self.assertEqual(self.post({'etapa': 'bot.intro', 'extra': 1}, HTTP_X_SESSAO_ID=self.sid).status_code, 400)
        r = self.post({'etapa': 'nada'}, HTTP_X_SESSAO_ID=self.sid)
        self.assertEqual((r.status_code, r.json()['erro']), (400, 'etapa'))
        self.assertEqual(self.c.get('/api/v1/context-agent/conversas/interacao/').status_code, 405)
        self.assertEqual(self.c.get('/api/v1/context-agent/conversas/avaliacoes/resumo/?data=ontem').status_code, 400)


if __name__ == '__main__':
    unittest.main()
