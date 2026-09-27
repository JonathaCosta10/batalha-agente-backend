"""Contrato das 4 rotas de conversa, pelo Django test client. Sem rede, sem BigQuery, sem Gemini reais.

1. POST /api/v1/context-agent/primeira-chamada/      -> PrimeiraChamadaTest
2. POST /api/v1/context-agent/enviar-mensagem/       -> EnviarMensagemTest   (410 Gone, Decisão D-3; I1 resolvido)
3. /api/v1/context-agent/conversas/sessao/ e mensagens/ -> ConversasMensagensTest
4. POST /api/v1/context-agent/conversas/interacao/   -> InteracaoTest        (I5 resolvido pela f7 em 2026-09-27; era expectedFailure)

Transporte Google substituído por dublês (urlopen falso ou Transporte com contador); fontes de dados são funções
falsas com contador. Cada bloco tem prova negativa: um caso ruim que o guard TEM de reprovar.
O enviar-mensagem gravava em ConversaAgenteSessao (hoje responde 410 e os testes conferem que nada é gravado), por isso este módulo cria um banco de teste em memória pelas
migrações (mesmo padrão de tests/test_semantica_backend.py; não toca no db.sqlite3).
"""
import json
import logging
import os
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from conversas_apoio import EDUARDO, MARIA, PERFIL, SELO, FakeGateway, contexto_com, fonte_falsa, fonte_quebrada, payload

from django.test import Client, override_settings  # noqa: E402
from django.test.utils import setup_databases, setup_test_environment, teardown_databases, teardown_test_environment  # noqa: E402

from apps.context_agent_datadriven.models import ConversaAgenteSessao, MensagemAgenteRegistro  # noqa: E402
from apps.context_agent_datadriven.services import perfil_usuario as pu  # noqa: E402
from apps.context_agent_datadriven.services import usuario_real  # noqa: E402
from apps.conversas import interacao, interacao_avaliacao as av, views  # noqa: E402
from apps.conversas.interacao_cenarios import FORA_DO_CONTEXTO  # noqa: E402
from apps.conversas.service import ConversationService  # noqa: E402

REAL_928 = '00928aaa-0000-4000-8000-000000000928'
CSV = ('indice,id_usuario,nome,genero,movimentos,meses,primeiro_anomes,ultimo_anomes\n'
       f'1,{MARIA},Maria,F,433,12,202501,202512\n'
       f'2,{EDUARDO},Eduardo,M,750,12,202501,202512\n'
       f'928,{REAL_928},Joana,F,500,12,202501,202512\n')
NOME_DEMO_928 = 'Eduarda Soares'  # cliente_id 928 do SQLite demo (services/usuario_real.py:6)

SEM_CHAVE = {'API_KEY_SECRECT': '', 'GEMINI_API_KEY': '', 'GSCONSOLE_SECRET': '', 'GOOGLE_API_KEY': '',
             'SECRETS_FILE': str(Path(tempfile.gettempdir()) / 'nao-existe' / '.secrets')}
CHAVE_TESTE = 'AIzaSyTESTE-chave-falsa-0123456789abcd'
COM_CHAVE = {**SEM_CHAVE, 'API_KEY_SECRECT': CHAVE_TESTE}

_estado_bd = None


def setUpModule():
    global _estado_bd
    logging.getLogger('django.request').setLevel(logging.ERROR)
    setup_test_environment()
    _estado_bd = setup_databases(verbosity=0, interactive=False)


def tearDownModule():
    teardown_databases(_estado_bd, verbosity=0)
    teardown_test_environment()


class CsvTemporario(unittest.TestCase):
    """perfil-usuario lê um CSV temporário (Maria=1, Eduardo=2, Joana=928); nada do data/ real."""

    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        csv = Path(pasta.name) / 'usuarios_verdade.csv'
        csv.write_text(CSV, encoding='utf-8')
        p = mock.patch.object(pu, 'ARQUIVO_CSV', csv)
        p.start()
        self.addCleanup(p.stop)
        pu._base['mtime'] = None
        self.addCleanup(pu._base.__setitem__, 'mtime', None)
        usuario_real.cache.limpar()
        self.addCleanup(usuario_real.cache.limpar)


class RespostaGoogle:
    """Resposta falsa de urlopen (generateContent)."""
    status = 200

    def __init__(self, texto='Resposta do modelo'):
        self.texto = texto

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({'candidates': [{'content': {'parts': [{'text': self.texto}]}}]}).encode('utf-8')


# =================================================================== 1. primeira-chamada
URL_PRIMEIRA = '/api/v1/context-agent/primeira-chamada/'


class PrimeiraChamadaTest(CsvTemporario):
    def post(self, corpo, **extra):
        return Client().post(URL_PRIMEIRA, data=json.dumps(corpo), content_type='application/json', **extra)

    def test_so_texto_inicial_vai_ao_modelo(self):
        """A carga Google é exatamente o texto_inicial: sem system_instruction, histórico, perfil nem nome."""
        sid = pu.definir_usuario(MARIA)['sessao_id']
        with mock.patch.dict(os.environ, COM_CHAVE), \
                mock.patch('urllib.request.urlopen', return_value=RespostaGoogle('Oi!')) as abrir:
            r = self.post({'texto_inicial': '  Olá, quanto gastei?  '}, HTTP_X_SESSAO_ID=sid)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(abrir.call_count, 1)
        carga = json.loads(abrir.call_args.args[0].data)
        self.assertEqual(carga, {'contents': [{'role': 'user', 'parts': [{'text': 'Olá, quanto gastei?'}]}]})
        bruto = abrir.call_args.args[0].data.decode('utf-8')
        for vazamento in ('Maria', MARIA, 'Vulnerável', 'system_instruction', 'history'):
            self.assertNotIn(vazamento, bruto)
        corpo = r.json()
        self.assertEqual((corpo['sucesso'], corpo['resposta']), (True, 'Oi!'))
        self.assertGreaterEqual(corpo['tempo_resposta_ms'], 0)

    def test_segunda_chamada_nao_carrega_a_primeira(self):
        """Duas chamadas seguidas: a segunda não leva a primeira mensagem (sem memória por desenho)."""
        with mock.patch.dict(os.environ, COM_CHAVE), \
                mock.patch('urllib.request.urlopen', return_value=RespostaGoogle()) as abrir:
            self.post({'texto_inicial': 'primeira mensagem'})
            self.post({'texto_inicial': 'segunda mensagem'})
        segunda = json.loads(abrir.call_args_list[1].args[0].data)
        self.assertEqual(len(segunda['contents']), 1)
        self.assertNotIn('primeira', json.dumps(segunda))

    def test_prova_negativa_campo_extra_vazio_ou_longo_da_400_sem_chamar_google(self):
        """Prova negativa: campo extra, vazio, só espaços, não-texto, lista ou >2000 caracteres dão 400 e zero chamadas."""
        ruins = [{'texto_inicial': 'oi', 'historico': []}, {'texto_inicial': 'oi', 'perfil': {'nome': 'Maria'}},
                 {}, {'texto_inicial': ''}, {'texto_inicial': '   '}, {'texto_inicial': 7},
                 {'texto_inicial': 'x' * 2001}, ['oi']]
        with mock.patch.dict(os.environ, COM_CHAVE), mock.patch('urllib.request.urlopen') as abrir:
            for corpo in ruins:
                with self.subTest(corpo=str(corpo)[:40]):
                    r = self.post(corpo)
                    self.assertEqual(r.status_code, 400, r.content)
                    self.assertEqual(set(r.json()), {'erro', 'tempo_resposta_ms'})
        abrir.assert_not_called()

    def test_limite_2000_e_inclusivo(self):
        """Exatamente 2000 caracteres é aceito (a fronteira do 400 é 2001)."""
        with mock.patch.dict(os.environ, COM_CHAVE), mock.patch('urllib.request.urlopen', return_value=RespostaGoogle()):
            self.assertEqual(self.post({'texto_inicial': 'x' * 2000}).status_code, 200)

    def test_sem_chave_503_sem_chamar_google(self):
        """Sem API_KEY_SECRECT: 503 com erro que cita a chave, e nenhuma chamada de rede."""
        with mock.patch.dict(os.environ, SEM_CHAVE), mock.patch('urllib.request.urlopen') as abrir:
            r = self.post({'texto_inicial': 'Olá'})
        self.assertEqual(r.status_code, 503)
        self.assertIn('API_KEY_SECRECT', r.json()['erro'])
        self.assertNotIn('resposta', r.json())
        abrir.assert_not_called()


# =================================================================== 2. enviar-mensagem
URL_ENVIAR = '/api/v1/context-agent/enviar-mensagem/'


GONE = {'erro': 'rota_descontinuada', 'usar': '/api/v1/context-agent/conversas/interacao/'}


class EnviarMensagemTest(CsvTemporario):
    """Decisão D-3, 2026-09-27: a rota antiga responde 410 Gone e aponta conversas/interacao/.

    Os casos são os mesmos de antes (sem identidade, X-Sessao-Id real, sem chave, modelo que vaza, corpo
    inválido, I1); o comportamento decidido é: 410 com o JSON fixo, nenhum modelo chamado, nada gravado.
    """

    def setUp(self):
        super().setUp()
        from django.db import transaction
        self._atomic = transaction.atomic()
        self._atomic.__enter__()

        def desfazer():
            transaction.set_rollback(True)
            self._atomic.__exit__(None, None, None)
        self.addCleanup(desfazer)
        self.real = pu.definir_usuario(REAL_928)['sessao_id']

    def post(self, corpo, **extra):
        return Client().post(URL_ENVIAR, data=json.dumps(corpo), content_type='application/json', **extra)

    def assert_gone(self, r, abrir=None):
        self.assertEqual(r.status_code, 410, r.content)
        self.assertEqual(r.json(), GONE)
        if abrir is not None:
            abrir.assert_not_called()
        self.assertEqual(ConversaAgenteSessao.objects.count(), 0)
        self.assertEqual(MensagemAgenteRegistro.objects.count(), 0)

    def test_sem_identidade_no_corpo_usa_cliente_demo_42(self):
        """Decisão D-3, 2026-09-27: antes atendia 'Cliente Itaú (#42)'; agora 410 e nenhuma sessão demo criada."""
        with mock.patch.dict(os.environ, COM_CHAVE), \
                mock.patch('urllib.request.urlopen', return_value=RespostaGoogle('Olá!')) as abrir:
            r = self.post({'mensagem': 'oi'})
        self.assert_gone(r, abrir)

    def test_x_sessao_id_do_usuario_real_e_ignorado(self):
        """Decisão D-3, 2026-09-27: com X-Sessao-Id do real 928 a rota não fala mais com ninguém: 410."""
        with mock.patch.dict(os.environ, COM_CHAVE), \
                mock.patch('urllib.request.urlopen', return_value=RespostaGoogle('Olá!')) as abrir:
            r = self.post({'mensagem': 'quem sou eu?', 'cliente_id': 928, 'cliente_nome': NOME_DEMO_928},
                          HTTP_X_SESSAO_ID=self.real)
        self.assert_gone(r, abrir)

    def test_sem_modelo_503_contingencia_rotulada_e_nada_gravado(self):
        """Decisão D-3, 2026-09-27: sem chave já não há contingência (era 503): 410, nada gravado."""
        with mock.patch.dict(os.environ, SEM_CHAVE), mock.patch('urllib.request.urlopen') as abrir:
            r = self.post({'mensagem': 'quero investir', 'cliente_id': 7})
        self.assert_gone(r, abrir)

    def test_prova_negativa_modelo_que_vaza_score_nao_sai(self):
        """Decisão D-3, 2026-09-27. Prova negativa: um modelo que vazaria 'score: 187' nem é chamado; o texto não sai."""
        with mock.patch.dict(os.environ, COM_CHAVE), \
                mock.patch('urllib.request.urlopen', return_value=RespostaGoogle('Seu score: 187')) as abrir:
            r = self.post({'mensagem': 'qual meu score?', 'cliente_id': 3})
        self.assert_gone(r, abrir)
        self.assertNotIn('score: 187', r.content.decode('utf-8'))

    def test_prova_negativa_corpo_invalido_400(self):
        """Decisão D-3, 2026-09-27: corpo inválido não é mais validado (era 400); qualquer corpo recebe o mesmo 410."""
        with mock.patch.dict(os.environ, SEM_CHAVE):
            for corpo in ({}, {'mensagem': '  '}, {'mensagem': 'oi', 'cliente_id': True}):
                with self.subTest(corpo=corpo):
                    self.assert_gone(self.post(corpo))

    def test_i1_usuario_real_nao_recebe_dados_do_cliente_demo(self):
        """I1, Decisão D-3, 2026-09-27 (era expectedFailure): com sessão do real 928, nada do demo e 410."""
        # O bug do docs/backlog.md (I1): o front mandava cliente_id=928 e o nome do demo; a contingência
        # cumprimentava "Olá, Eduarda Soares!" a pessoa real 928 (Joana no CSV de teste).
        with mock.patch.dict(os.environ, SEM_CHAVE), mock.patch('urllib.request.urlopen') as abrir:
            r = self.post({'mensagem': 'oi', 'cliente_id': 928, 'cliente_nome': NOME_DEMO_928},
                          HTTP_X_SESSAO_ID=self.real)
        self.assert_gone(r, abrir)
        corpo = r.content.decode('utf-8')
        self.assertNotIn('Eduarda', corpo)
        self.assertNotIn('Joana', corpo)
        self.assertFalse(ConversaAgenteSessao.objects.filter(cliente_id=928).exists(),
                         'a pessoa real 928 foi gravada como sessão do cliente demo 928 no SQLite')

    def test_prova_negativa_guard_do_410_reprova_resposta_antiga(self):
        """Decisão D-3, 2026-09-27. Prova negativa: a resposta antiga (200 com cliente demo) reprova no assert_gone."""
        antiga = mock.Mock(status_code=200, content=b'{"resposta_agente": "Ola, Eduarda Soares!"}')
        antiga.json.return_value = {'resposta_agente': 'Olá, Eduarda Soares!'}
        with self.assertRaises(AssertionError):
            self.assert_gone(antiga)


# =================================================================== 3. conversas/sessao + mensagens
URL_MSG = '/api/v1/context-agent/conversas/mensagens/'
URL_BOOT = '/api/v1/context-agent/conversas/sessao/'


class GastoGateway(FakeGateway):
    """Responde com um valor e a claim 'outflows' que o sustentaria."""

    def __init__(self, valor='10790.43'):
        super().__init__('Pelo extrato, você gasta em média R$ 10.790,43 por mês.')
        self.valor = valor

    async def generate(self, message, context, history, constraints, titular=None):
        draft = await super().generate(message, context, history, constraints, titular=titular)
        draft['claims'] = [{'kind': 'financial', 'evidence_id': 'outflows', 'text': 'gasto médio mensal', 'value': self.valor}]
        return draft


class ConversasMensagensTest(CsvTemporario):
    def setUp(self):
        super().setUp()
        self.maria = pu.definir_usuario(MARIA)['sessao_id']

    def servico(self, service):
        p = mock.patch.object(views, 'get_service', lambda: service)
        p.start()
        self.addCleanup(p.stop)
        return service

    def cliente(self):
        c = Client()
        self.assertEqual(c.get(URL_BOOT + '?sessao_id=' + self.maria).status_code, 200)
        return c

    def post(self, client, body, **extra):
        return client.post(URL_MSG, data=json.dumps(body), content_type='application/json', **extra)

    def test_sem_sessao_404_no_envelope_1_0(self):
        """Sem sessão (nenhuma, inexistente, ou POST sem cookie): 404 no envelope 1.0 pedindo definir/."""
        gateway = self.servico(ConversationService(gateway=FakeGateway())).gateway
        for r in (Client().get(URL_BOOT), Client().get(URL_BOOT + '?sessao_id=nao-existe'),
                  self.post(Client(), payload()), self.post(Client(), payload(), HTTP_X_SESSAO_ID='x' * 65)):
            with self.subTest(status=r.status_code):
                self.assertEqual(r.status_code, 404)
                c = r.json()
                self.assertEqual((c['schema_version'], c['status']), ('1.0', 'unavailable'))
                self.assertIn('perfil-usuario/definir/', c['reply'])
        self.assertEqual(gateway.calls, [])

    def test_prova_negativa_post_sem_csrf_403(self):
        """Prova negativa: POST mensagens/ com cookie de sessão mas sem X-CSRFToken é 403 no envelope, sem modelo."""
        gateway = self.servico(ConversationService(gateway=FakeGateway(), context_builder=contexto_com(fonte_falsa))).gateway
        client = Client(enforce_csrf_checks=True)
        client.get(URL_BOOT + '?sessao_id=' + self.maria)
        r = self.post(client, payload())
        self.assertEqual((r.status_code, r.json()['schema_version'], r.json()['status']), (403, '1.0', 'unavailable'))
        self.assertEqual(gateway.calls, [])
        ok = self.post(client, payload(), HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertEqual(ok.status_code, 200)

    def test_historico_enviado_ao_modelo_e_limitado_a_12(self):
        """O modelo recebe no máximo as últimas 12 entradas (6 turnos) do histórico, mesmo após 8 turnos."""
        gateway = FakeGateway()
        self.servico(ConversationService(gateway=gateway, context_builder=contexto_com(fonte_falsa), requests_per_minute=100))
        client, cid = self.cliente(), None
        for i in range(8):
            r = self.post(client, payload(f'pergunta {i}', mid=f'msg-{i}', cid=cid))
            self.assertEqual(r.status_code, 200, r.content)
            cid = r.json()['conversation_id']
        ultimo = [c for c in gateway.calls if c[0] == 'generate'][-1][2]
        self.assertEqual(len(ultimo), 12)
        self.assertEqual(ultimo[0]['text'], 'pergunta 1')  # 'pergunta 0' já saiu da janela

    def test_prova_negativa_limite_de_turnos_429(self):
        """Prova negativa: passado max_turns, o turno seguinte é 429 e não chama o modelo."""
        gateway = FakeGateway()
        self.servico(ConversationService(gateway=gateway, context_builder=contexto_com(fonte_falsa), max_turns=2))
        client, cid = self.cliente(), None
        for i in range(2):
            cid = self.post(client, payload(f'p{i}', mid=f'm{i}', cid=cid)).json()['conversation_id']
        antes = len(gateway.calls)
        r = self.post(client, payload('p2', mid='m2', cid=cid))
        self.assertEqual(r.status_code, 429)
        self.assertEqual(len(gateway.calls), antes)

    def test_resposta_aprovada_traz_estado_medido_e_selo(self):
        """Resposta aprovada com número medido traz dados.estado MEDIDO e o selo (fonte, medido_em)."""
        self.servico(ConversationService(gateway=GastoGateway(), context_builder=contexto_com(fonte_falsa)))
        r = self.post(self.cliente(), payload('quanto eu gasto por mês?'))
        self.assertEqual(r.status_code, 200, r.content)
        dados = r.json()['dados']
        self.assertEqual(dados['estado'], 'MEDIDO')
        self.assertEqual((dados['selo']['fonte'], dados['selo']['medido_em']), (SELO['fonte'], SELO['medido_em']))

    def test_fonte_falhando_e_nao_medido_sem_numero(self):
        """Fonte de dados fora: dados = NAO_MEDIDO sem selo, e o modelo não recebe fato nenhum (nem zero)."""
        gateway = FakeGateway()
        self.servico(ConversationService(gateway=gateway, context_builder=contexto_com(fonte_quebrada)))
        r = self.post(self.cliente(), payload('quanto eu gasto por mês?'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['dados'], {'estado': 'NAO_MEDIDO', 'selo': None})
        contexto = [c for c in gateway.calls if c[0] == 'generate'][0][1]
        self.assertEqual(contexto['facts'], [])
        self.assertNotIn('0.00', json.dumps(contexto))

    def test_prova_negativa_zero_inventado_com_fonte_fora_nao_sai(self):
        """Prova negativa: fonte fora + modelo que afirma gasto R$ 0,00 com claim: não sai como 200 medido."""
        self.servico(ConversationService(gateway=GastoGateway(valor='0.00'), context_builder=contexto_com(fonte_quebrada)))
        r = self.post(self.cliente(), payload('quanto eu gasto por mês?'))
        self.assertNotEqual(r.status_code, 200, r.content)
        self.assertNotIn('10.790,43', r.content.decode('utf-8'))

    def test_prova_negativa_claim_diferente_do_medido_503(self):
        """Prova negativa: claim com valor diferente do medido é recusada (503), nunca liberada."""
        self.servico(ConversationService(gateway=GastoGateway(valor='9999.99'), context_builder=contexto_com(fonte_falsa)))
        self.assertEqual(self.post(self.cliente(), payload('quanto eu gasto por mês?')).status_code, 503)


# =================================================================== 4. conversas/interacao
URL_INT = '/api/v1/context-agent/conversas/interacao/'
M1, M2 = 'gemini-flash-latest', 'gemini-3.5-flash-lite'
JANELA = 'janeiro de 2025 a novembro de 2025'
BOM_SOBROU = (f'Maria, na média mensal de {JANELA} sobrou R$ 1.518,23 por mês: entraram R$ 9.690,58 e saíram '
              'R$ 8.172,35. Vamos organizar o próximo passo.')
INVENTADO = (f'Maria, na média mensal de {JANELA} sobrou R$ 4.321,00 por mês: entraram R$ 9.690,58 e saíram '
             'R$ 8.172,35. Vamos organizar o próximo passo.')
SELO_M = {**SELO, 'jobs': {'mensal_50_30_20': 'job-teste'}, 'data_corte': '2025-12-22'}


def _mes(anomes, e, s):
    return {'anomes': anomes, 'entradas': e, 'saidas': s, 'necessidades': 6000.0, 'desejos': 1000.0,
            'futuro_programado': 10.0, 'fora_da_regra': 1500.0, 'saidas_sem_classe': 0}


LINHAS = [_mes(202500 + m, 9800.0, 8000.0) for m in range(1, 11)] + [_mes(202511, 8596.41, 9895.85)]


class Transporte:
    """Dublê do generateContent com contador; guard de entrada devolve 'allow'."""

    def __init__(self, textos):
        self.textos, self.chamadas = textos, []

    def __call__(self, modelo, corpo):
        self.chamadas.append((modelo, corpo))
        props = corpo['generationConfig']['responseJsonSchema'].get('properties', {})
        out = ({'decision': 'allow', 'reason_codes': [], 'constraints': [], 'policy_version': '1.0'}
               if 'decision' in props else {'texto': self.textos.get(modelo, '')})
        return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(out, ensure_ascii=False)}]}}],
                'usageMetadata': {'promptTokenCount': 900, 'candidatesTokenCount': 60, 'totalTokenCount': 960},
                'modelVersion': f'{modelo}-fake'}

    def redacoes(self):
        return [c for c in self.chamadas if 'decision' not in c[1]['generationConfig']['responseJsonSchema'].get('properties', {})]


class InteracaoTest(CsvTemporario):
    def setUp(self):
        super().setUp()
        self.pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.sid = pu.definir_usuario(MARIA)['sessao_id']
        self.consultas = {'perfil': 0, 'mensal': 0, 'proposta': 0, 'subcategorias': 0}

        def conta(nome, valor):
            def fonte(codigo):
                self.consultas[nome] += 1
                if isinstance(valor, Exception):
                    raise valor
                return deepcopy(valor)
            return fonte
        fontes = {'perfil': conta('perfil', PERFIL), 'mensal': conta('mensal', (LINHAS, SELO_M)),
                  'proposta': conta('proposta', RuntimeError('sem ADC')),
                  'subcategorias': conta('subcategorias', RuntimeError('sem ADC'))}
        self.trans = Transporte({M1: BOM_SOBROU})
        for p in (mock.patch.dict(interacao.FONTES, fontes),
                  mock.patch.object(interacao, 'gateway_para',
                                    lambda m, t=None, b=300: interacao.GatewayInteracao(model=m, transporte=self.trans)),
                  mock.patch.object(av, 'PASTA_LEDGER', Path(self.pasta))):
            p.start()
            self.addCleanup(p.stop)

    def post(self, corpo, sid=True):
        extra = {'HTTP_X_SESSAO_ID': self.sid} if sid else {}
        return Client().post(URL_INT, data=json.dumps(corpo), content_type='application/json', **extra)

    def total_consultas(self):
        return sum(self.consultas.values())

    def test_sem_x_sessao_id_401(self):
        """Sem header X-Sessao-Id: 401 'sessao', sem consulta e sem modelo (cookie não vale aqui)."""
        r = self.post({'etapa': 'bot.intro'}, sid=False)
        self.assertEqual((r.status_code, r.json()['erro'], r.json()['schema_version']), (401, 'sessao', '1.1'))  # D-15/D9 (f7, 2026-09-27): schema_version único 1.1
        self.assertEqual((self.total_consultas(), len(self.trans.chamadas)), (0, 0))

    def test_prova_negativa_etapa_invalida_400_com_etapas_validas(self):
        """Prova negativa: etapa desconhecida é 400 'etapa' com a lista etapas_validas, sem consulta nem modelo."""
        r = self.post({'etapa': 'etapa.que.nao.existe'})
        self.assertEqual((r.status_code, r.json()['erro']), (400, 'etapa'))
        self.assertEqual(r.json()['etapas_validas'], sorted(interacao.ETAPAS))
        self.assertIn('intro.carrossel.1', r.json()['etapas_validas'])
        self.assertEqual((self.total_consultas(), len(self.trans.chamadas)), (0, 0))

    def test_extremo_autolesao_encaminha_sem_modelo_nem_fonte(self):
        """Mensagem de autolesão: origem 'encaminhamento' (humano), zero chamadas ao modelo e zero consultas."""
        r = self.post({'etapa': 'intro.carrossel.1', 'mensagem': 'não aguento mais essas dívidas, quero morrer'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        c = r.json()
        self.assertEqual((c['origem_resposta'], c['dominio'], c['aprovado']), ('encaminhamento', 'extremo', True))
        self.assertEqual((c['encaminhamento']['motivo'], c['encaminhamento']['destino']), ('autolesao', 'humano'))
        self.assertTrue(c['texto'])
        self.assertEqual(self.trans.chamadas, [])
        self.assertEqual(self.total_consultas(), 0)
        self.assertEqual(c['selo'], {})

    def test_fora_do_dominio_resposta_fixa_sem_modelo(self):
        """Pergunta fora do contexto financeiro: resposta FIXA, origem 'fora_do_contexto', sem modelo nem consulta."""
        r = self.post({'etapa': 'intro.carrossel.1', 'mensagem': 'qual time ganhou o campeonato ontem?'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        c = r.json()
        self.assertEqual((c['texto'], c['origem_resposta'], c['dominio']), (FORA_DO_CONTEXTO, 'fora_do_contexto', 'fora'))
        self.assertEqual((len(self.trans.chamadas), self.total_consultas()), (0, 0))

    def test_resposta_aprovada_do_modelo_traz_selo(self):
        """Texto do modelo com os números medidos: aprovado, origem 'modelo' e selo com o job da consulta."""
        r = self.post({'etapa': 'intro.carrossel.1'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        c = r.json()
        self.assertEqual((c['origem_resposta'], c['aprovado'], c['situacao']), ('modelo', True, 'SOBROU'))
        self.assertEqual(c['selo']['mensal']['jobs'], {'mensal_50_30_20': 'job-teste'})

    def test_prova_negativa_modelo_que_inventa_numero_cai_no_roteiro(self):
        """Prova negativa: os dois modelos inventam R$ 4.321,00; ambos reprovados e sai o roteiro com o valor medido."""
        self.trans.textos = {M1: INVENTADO, M2: INVENTADO}
        r = self.post({'etapa': 'intro.carrossel.1'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        c = r.json()
        self.assertEqual((c['origem_resposta'], c['aprovado']), ('roteiro', True))
        self.assertNotIn('4.321', c['texto'])
        self.assertIn('1.518,23', c['texto'])
        t1, t2 = c['avaliacao']['tentativas']
        self.assertEqual((t1['aprovado'], t2['aprovado']), (False, False))
        self.assertTrue(t1['reprovados'], 'a tentativa com número inventado tem de listar o guard que reprovou')
        self.assertEqual(len(self.trans.redacoes()), 2)

    def test_fonte_fora_e_nao_medido_sem_numero(self):
        """Fontes fora: situação NAO_MEDIDO e nenhum valor inventado (entradas/saídas None, nunca 0)."""
        for nome in ('perfil', 'mensal'):
            interacao.FONTES[nome] = lambda c: (_ for _ in ()).throw(RuntimeError('sem ADC'))
        self.trans.textos = {M1: 'Maria, ainda não consegui ler os seus números. Vamos com calma.'}
        r = self.post({'etapa': 'intro.carrossel.1'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        c = r.json()
        self.assertEqual((c['situacao'], c['perfil_t3'], c['origem_resposta']), ('NAO_MEDIDO', 'NAO_MEDIDO', 'modelo'))
        self.assertNotRegex(c['texto'], r'\d')
        self.assertTrue(c['estado_dados']['mensal'].startswith('NAO_MEDIDO'))
        ref = c['dados']['mes_referencia']
        self.assertEqual((ref['entradas'], ref['saidas'], ref['saldo']), (None, None, None))

    def test_modo_demo_nao_chama_modelo(self):
        """CONVERSAS.MODO=demo: zero chamadas ao modelo; resposta vem do roteiro, rotulada."""
        with override_settings(CONVERSAS={'MODO': 'demo'}):
            r = self.post({'etapa': 'intro.carrossel.1'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        c = r.json()
        self.assertEqual(c['origem_resposta'], 'roteiro')
        self.assertIn('demo', c['avaliacao']['motivo_fallback'])
        self.assertEqual(self.trans.chamadas, [])

    def test_i5_pergunta_de_seguimento_precisa_do_turno_anterior(self):
        """I5 — pergunta de seguimento precisa do turno anterior: o 2.º POST tem de levar o referente do 1.º ao modelo."""
        self.trans.textos = {M1: 'Maria, ainda não tenho essa informação.'}
        self.post({'etapa': 'livre.respostas', 'mensagem': 'quanto gastei com delivery?'})
        n = len(self.trans.redacoes())
        self.assertGreater(n, 0, 'o 1.º turno tem de chegar ao modelo')
        self.post({'etapa': 'livre.respostas', 'mensagem': 'e em fevereiro, quanto gastei?'})
        segunda = self.trans.redacoes()[n:]
        self.assertTrue(segunda, 'o 2.º turno tem de chegar ao modelo')
        self.assertIn('delivery', json.dumps(segunda[0][1], ensure_ascii=False).lower())


if __name__ == '__main__':
    unittest.main()
