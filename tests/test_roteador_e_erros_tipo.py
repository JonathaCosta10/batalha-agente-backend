"""Router de modelos por etapa/erro e códigos de erro estáveis para o front (backend-22, dono 2026-09-27 12:38/12:39).

- Router (apps/conversas/roteador.py + desafio_itau/politica/cotas-gemini-v1.json): 429 no primeiro -> responde o
  segundo; resfriamento respeitado sem chamada; 400 não troca; timeout -> o mais rápido; todos falham -> tipo
  cota_provedor/timeout_provedor com HTTP coerente.
- erros_api 1.2.0: todo erro de conversas/* e i-agora/* sai com erro_api.tipo e erro_api.codigo numérico, nunca null.
- GET /api/health/ (alias do /healthz).
Nada chama rede: transporte, relógio e fonte do extrato são dublês.
"""
import copy
import json
import unittest
from unittest.mock import patch

import conversas_apoio  # noqa: F401  (django.setup)
from conversas_apoio import FakeGateway, payload, run
from i_agora_apoio import ROOT, IAgoraBase

from django.test import Client

from apps.conversas import roteador as rt
from apps.conversas import views
from apps.conversas.gateway import ErroProvedor, GeminiGateway
from apps.conversas.service import ConversationService
from desafio_itau.politica import erros_api

G = rt.carregar().router.etapas['input_guard']       # ordem dos guards
GEN = rt.carregar().router.etapas['generate']        # ordem do generate


def ok_guard(modelo):
    return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text':
            '{"decision":"allow","reason_codes":[],"constraints":[],"policy_version":"1.0"}'}]}}],
            'modelVersion': modelo}


class Relogio:
    def __init__(self):
        self.t = 5000.0

    def __call__(self):
        return self.t


def gateway(erros, relogio=None):
    """erros: {modelo: exceção}; os outros respondem."""
    chamadas, relogio = [], relogio or Relogio()

    def transporte(modelo, corpo):
        chamadas.append(modelo)
        if erros.get(modelo):
            raise erros[modelo]
        return ok_guard(modelo)
    g = GeminiGateway(transporte=transporte, roteador=rt.Roteador(relogio=relogio))
    return g, chamadas, relogio


class DadosDoRouter(unittest.TestCase):
    def test_ordem_vem_dos_dados_e_so_de_modelos_aptos(self):
        dados = rt.carregar()
        self.assertEqual(G[0], 'gemini-3.1-flash-lite')       # guards fora da cota do principal
        self.assertEqual(GEN[0], 'gemini-3.5-flash-lite')     # generate no principal
        for ordem in dados.router.etapas.values():
            self.assertTrue(all(dados.modelos[m].apto for m in ordem))

    def test_prova_negativa_modelo_nao_apto_na_ordem_reprova(self):
        bruto = json.loads(rt.ARQUIVO.read_text(encoding='utf-8'))
        ruim = copy.deepcopy(bruto)
        ruim['router']['etapas']['generate'].append('gemma-4-31b-it')   # 400 com o corpo real
        with self.assertRaises(ValueError):
            rt.validar(ruim)
        ruim = copy.deepcopy(bruto)
        ruim['router']['etapas']['input_guard'] = []
        with self.assertRaises(ValueError):
            rt.validar(ruim)
        rt.validar(bruto)  # o ficheiro real passa


class RouterPorErro(unittest.TestCase):
    def test_429_no_primeiro_responde_o_segundo_e_resfriamento_e_respeitado(self):
        g, chamadas, _ = gateway({G[0]: ErroProvedor(429, 'minuto', 35)})
        run(g.input_guard('oi', []))
        self.assertEqual(chamadas, [G[0], G[1]])
        self.assertEqual(g.roteador.estado()['resfriamentos'][G[0]], {'restam_s': 35, 'motivo': 'cota_minuto'})
        run(g.input_guard('oi', []))
        self.assertEqual(chamadas, [G[0], G[1], G[1]])   # o primeiro não foi chamado de novo
        self.assertEqual(g.calls, 3)
        self.assertEqual(g.roteador.estado()['ultimo_modelo_por_etapa']['input_guard'], G[1])

    def test_depois_do_resfriamento_volta_ao_primeiro(self):
        g, chamadas, relogio = gateway({G[0]: ErroProvedor(429, 'dia')})
        run(g.input_guard('oi', []))
        relogio.t += rt.carregar().router.resfriamento_s.cota_dia + 1
        g.transporte = lambda modelo, corpo: (chamadas.append(modelo), ok_guard(modelo))[1]
        g._com_timeout = False
        run(g.input_guard('oi', []))
        self.assertEqual(chamadas[-1], G[0])

    def test_prova_negativa_400_nao_troca_de_modelo(self):
        g, chamadas, _ = gateway({G[0]: ErroProvedor(400)})
        with self.assertRaises(ErroProvedor):
            run(g.input_guard('oi', []))
        self.assertEqual(chamadas, [G[0]])
        self.assertEqual(g.roteador.estado()['resfriamentos'], {})   # erro nosso não resfria o modelo

    def test_timeout_vai_para_o_mais_rapido(self):
        dados = rt.carregar()
        g, chamadas, _ = gateway({G[0]: TimeoutError()})
        run(g.input_guard('oi', []))
        restantes = [m for m in G if m != G[0]]
        rapido = min(restantes, key=lambda m: (dados.modelos[m].latencia_ref_ms or 10 ** 9, G.index(m)))
        self.assertEqual(chamadas, [G[0], rapido])

    def test_503_em_todos_cada_modelo_no_maximo_uma_vez(self):
        """erros_api 1.4.0: segue a ordem inteira no prazo (antes: 1 nova chamada); nunca o mesmo modelo 2x."""
        g, chamadas, _ = gateway({m: ErroProvedor(503) for m in G})
        with self.assertRaises(ErroProvedor):
            run(g.input_guard('oi', []))
        self.assertEqual(sorted(chamadas), sorted(G))

    def test_todos_sem_cota_nenhuma_chamada_e_429(self):
        g, chamadas, _ = gateway({m: ErroProvedor(429, 'dia') for m in G})
        for _ in range(len(G)):
            try:
                run(g.input_guard('oi', []))
            except ErroProvedor:
                pass
        antes = len(chamadas)
        with self.assertRaises(ErroProvedor) as ctx:
            run(g.input_guard('oi', []))
        self.assertEqual((len(chamadas), ctx.exception.code), (antes, 429))
        self.assertEqual(set(g.cota_diaria_esgotada()), set(G))

    def test_teto_de_rpm_do_painel_desvia_antes_do_429(self):
        r = rt.Roteador(relogio=Relogio())
        rpm = r.dados.modelos['gemini-3.6-flash'].painel.rpm
        for _ in range(rpm - r.dados.router.rpm_margem):
            r.chamou('gemini-3.6-flash')
        self.assertEqual(r.bloqueio('gemini-3.6-flash'), 429)
        r.relogio.t += 61
        self.assertIsNone(r.bloqueio('gemini-3.6-flash'))

    def test_guards_e_generate_em_modelos_diferentes(self):
        g, chamadas, _ = gateway({})
        run(g.input_guard('oi', []))
        self.assertEqual(chamadas, [G[0]])
        self.assertNotEqual(G[0], GEN[0])


class VersaoDoContratoEDoServidor(unittest.TestCase):
    """Medido 12:58 BRT: gemini-3.1-flash-lite devolve policy_version '2026-09-27' (ignora o const do schema)."""

    def test_guard_com_policy_version_do_modelo_passa_carimbado(self):
        from apps.conversas.gateway import decisao_guard
        d = decisao_guard('{"decision":"allow","reason_codes":[],"constraints":[],"policy_version":"2026-09-27"}')
        self.assertEqual((d['decision'], d['policy_version']), ('allow', '1.0'))

    def test_prova_negativa_resto_do_guard_continua_estrito(self):
        from apps.conversas.gateway import decisao_guard
        for ruim in ('{"decision":"talvez","reason_codes":[],"constraints":[],"policy_version":"1.0"}',
                     '{"decision":"allow","reason_codes":[],"constraints":[],"policy_version":"1.0","x":1}',
                     '{"decision":"allow","reason_codes":["outro"],"constraints":[]}',
                     '["allow"]', 'nao json'):
            with self.subTest(ruim=ruim), self.assertRaises(ValueError):
                decisao_guard(ruim)

    def test_rascunho_do_generate_real_valida_sem_carimbo(self):
        """Saída real do gemini-3.1-flash-lite (13:03 BRT) no generate: valida no AgentDraftV1 sem ajuste."""
        from apps.conversas.schemas import AgentDraftV1
        d = AgentDraftV1.model_validate_json(json.dumps({
            'reply': 'Que excelente objetivo! Você já tem uma estimativa de quanto pretende reservar por mês?',
            'status': 'needs_clarification', 'capabilities': ['orcamento', 'reserva'], 'claims': [],
            'missing_data': ['valor_mensal_reserva', 'gasto_mensal_atual', 'mes_referencia'],
            'projection_proposal': None, 'commitment_proposal': None}))
        self.assertEqual(d.status, 'needs_clarification')
        with self.assertRaises(ValueError):   # prova negativa: campo extra continua proibido
            AgentDraftV1.model_validate_json('{"schema_version":"1.0","reply":"x"}')


class FrontRecebeTipoEHttp(unittest.TestCase):
    def servico(self, erro):
        fake = FakeGateway()
        g, chamadas, _ = gateway({m: erro for m in G})
        fake.input_guard = g.input_guard
        return ConversationService(gateway=fake), chamadas

    def test_todos_sem_cota_http_429_tipo_cota_provedor_e_retry_after(self):
        service, _ = self.servico(ErroProvedor(429, 'dia'))
        corpo, status = run(service.send('a', payload('oi')))
        self.assertEqual((status, corpo['erro_api']['tipo'], corpo['erro_api']['codigo']), (429, 'cota_provedor', 429))
        resposta = views.response((corpo, status))
        self.assertEqual(resposta['Retry-After'], str(corpo['erro_api']['tentar_novamente_em_s']))

    def test_todos_em_timeout_http_504_tipo_timeout_provedor(self):
        service, _ = self.servico(TimeoutError())
        corpo, status = run(service.send('a', payload('oi')))
        self.assertEqual((status, corpo['erro_api']['tipo'], corpo['erro_api']['codigo']), (504, 'timeout_provedor', 504))

    def test_provedor_fora_503_e_sem_status_nunca_null(self):
        for erro, codigo in ((ErroProvedor(503), 503), (ErroProvedor(500), 500), (RuntimeError('x'), 503)):
            with self.subTest(erro=repr(erro)):
                service, _ = self.servico(erro)
                corpo, status = run(service.send('a', payload('oi')))
                self.assertEqual((status, corpo['erro_api']['tipo'], corpo['erro_api']['codigo']),
                                 (503, 'provedor_indisponivel', codigo))

    def test_validacao_reprovada_tem_tipo_proprio(self):
        class Recusa(FakeGateway):
            async def output_guard(self, *a, **k):
                return {'decision': 'replace', 'reason_codes': ['unsupported'], 'constraints': [], 'policy_version': '1.0'}
        corpo, status = run(ConversationService(gateway=Recusa()).send('a', payload()))
        self.assertEqual((status, corpo['erro_api']['tipo']), (503, 'resposta_reprovada_validacao'))


class NenhumErroSemCodigo(unittest.TestCase):
    def test_prova_negativa_tabela_inteira_e_status_soltos(self):
        pol = erros_api.carregar()
        self.assertIn(pol.versao, ('1.2.0', '1.3.0', '1.4.0'))
        for tipo, t in pol.tipos.items():
            b = erros_api.erro_api(None, t.origem, tipo=tipo)
            with self.subTest(tipo=tipo):
                self.assertTrue(isinstance(b['codigo'], int) and b['tipo'] == tipo and b['acao_cliente'])
                self.assertNotIn('{', b['mensagem'])
        for status in (400, 401, 403, 404, 405, 409, 418, 429, 500, 503, 504, None):
            for origem in ('api', 'provedor'):
                b = erros_api.erro_api(status, origem, tipo=None if status else erros_api.tipo_de(status, origem))
                if b is None:
                    continue
                with self.subTest(status=status, origem=origem):
                    self.assertIsInstance(b['codigo'], int)
                    self.assertIn(b['tipo'], pol.tipos)
        self.assertFalse(erros_api.pode_nova_chamada(400))   # 1.2.0: 400 do provedor não troca
        for t in pol.erros.values():
            self.assertFalse(t.repetir_mesmo_pedido)

    def test_erros_http_da_conversa(self):
        service = ConversationService(gateway=FakeGateway())
        casos = [(service.send('a', {**payload(), 'extra': 1}), 400, 'schema'),
                 (service.send('a', payload(cid='nao-existe')), 404, 'nao_encontrado'),
                 (service.send(None, payload()), 401, 'sessao_ausente')]
        for coro, http, tipo in casos:
            corpo, status = run(coro)
            with self.subTest(tipo=tipo):
                self.assertEqual((status, corpo['erro_api']['tipo'], corpo['erro_api']['codigo']), (http, tipo, http))
        r = Client().post('/api/v1/context-agent/conversas/mensagens/', '{}', content_type='application/json')
        self.assertEqual((r.status_code, r.json()['erro_api']['tipo']), (404, 'sessao_ausente'))
        r = Client(enforce_csrf_checks=True).post('/api/v1/context-agent/conversas/mensagens/', '{}',
                                                  content_type='application/json')
        self.assertEqual((r.status_code, r.json()['erro_api']['tipo'], r.json()['erro_api']['acao_cliente']),
                         (403, 'csrf', 'reiniciar_sessao'))
        r = Client().get('/api/v1/context-agent/conversas/mensagens/')
        self.assertEqual((r.status_code, r.json()['erro_api']['tipo']), (405, 'metodo_nao_permitido'))

    def test_health_alias(self):
        for url in ('/api/health/', '/api/health', '/healthz'):
            r = Client().get(url)
            with self.subTest(url=url):
                self.assertEqual((r.status_code, r.json()), (200, {'status': 'ok'}))


class ErrosDoIAgora(IAgoraBase):
    def test_todo_erro_do_i_agora_tem_tipo_e_codigo(self):
        r = Client().get(ROOT + 'plano/')
        self.assertEqual((r.status_code, r.json()['erro_api']['tipo'], r.json()['codigo']), (401, 'sessao_ausente', 'auth'))
        c = self.session(csrf=True)
        self.profile(c)
        casos = [(self.send(c, 'post', 'plano/proposta/', {'clientRequestId': 'p1'}), 409, 'sem_proposta'),
                 (self.send(c, 'post', 'plano/confirmar/', {'x': 1}), 400, 'schema'),
                 (self.send(c, 'patch', 'plano/', {'version': 999, 'stage': 'card'}), 409, 'plano_desatualizado'),
                 (c.get(ROOT + 'acompanhamento/'), 404, 'sem_objetivo_confirmado'),
                 (self.send(c, 'put', 'plano/confirmar/', {}), 405, 'metodo_nao_permitido')]
        for r, http, tipo in casos:
            with self.subTest(tipo=tipo):
                self.assertEqual((r.status_code, r.json()['erro_api']['tipo'], r.json()['erro_api']['codigo']),
                                 (http, tipo, http))
        self.src.fail = 1
        self.send(c, 'post', 'sessao/abertura/', {'origem': 'fab', 'next': True})
        r = c.get(ROOT + 'perfil/')
        if r.status_code == 503:
            self.assertEqual(r.json()['erro_api']['tipo'], 'fonte_indisponivel')

    def test_status_expoe_roteador(self):
        g, _, _ = gateway({})
        with patch.object(views, 'get_service', return_value=ConversationService(gateway=g)):
            corpo = views.estado_harness()
        self.assertEqual(corpo['roteador']['ordem_por_etapa']['generate'], GEN)
        self.assertIn('resfriamentos', corpo['roteador'])


if __name__ == '__main__':
    unittest.main()
