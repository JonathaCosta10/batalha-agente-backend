"""Rotas /api/v1/context-agent/conversas/ (sessao/, mensagens/) + guards novos do porte, sem rede.

Portado de agente-app-mobile/agent_backend/tests/test_http.py e test_privacy.py (commit 1302ba5). A
identidade agora é o sessao_id de perfil-usuario/definir/ (CSV temporário). Os números vêm de
services/usuario_real com executor BigQuery falso (modelo: tests/test_usuario_real.py).

Provas negativas dos guards novos: sem sessão 404; sessão revogada 404 mesmo com payload em cache;
"quem sou eu" sem nome/código é REPROVADO e trocado pela resposta do CSV; claim com valor diferente
do medido reprova (503); BigQuery quebrado vira NAO_MEDIDO sem número; o código permitido do titular
não libera outro número com cara de cartão nem CPF.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from conversas_apoio import CSV, EDUARDO, MARIA, FakeGateway, contexto_com, fonte_falsa, payload

from django.test import Client

from apps.context_agent_datadriven.services import perfil_usuario as pu
from apps.context_agent_datadriven.services import usuario_real
from apps.conversas import views
from apps.conversas.rules import safe_text
from apps.conversas.service import ConversationService

URL = '/api/v1/context-agent/conversas/mensagens/'
BOOT = '/api/v1/context-agent/conversas/sessao/'


class ExecutorFalso:
    def executar(self, sql, parametros):
        self.ultimo_job = {'job_id': 'job-falso', 'bytes_processados': 10}
        if 'ROW_NUMBER' in sql:
            return [{'indice': i + 1, 'id_usuario': u, 'movimentos': 400, 'meses': 12,
                     'primeiro_anomes': 202501, 'ultimo_anomes': 202512} for i, u in enumerate([MARIA, EDUARDO])]
        if 'segmento_t3' in sql:
            return [{'meses': 11, 'inflow_mensal': 5000.0, 'outflow_mensal': 4500.0, 'surplus_mensal': 500.0,
                     'taxa_surplus_pct': 10.0, 'saidas_sem_grupo': 0, 'segmento_t3': 'Esbanjador'}]
        return [{'valor': 1.0}]


class ExecutorQuebrado:
    def executar(self, sql, parametros):
        raise ConnectionError('sem ADC')


class GastoGateway(FakeGateway):
    """Responde com o outflow medido e a claim que o sustenta."""
    def __init__(self, valor='10790.43'):
        super().__init__('Pelo extrato, você gasta em média R$ 10.790,43 por mês.')
        self.valor = valor

    async def generate(self, message, context, history, constraints, titular=None):
        draft = await super().generate(message, context, history, constraints, titular=titular)
        draft['claims'] = [{'kind': 'financial', 'evidence_id': 'outflows', 'text': 'gasto médio mensal', 'value': self.valor}]
        return draft


class ConversasHttpTest(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        csv = Path(self.pasta.name) / 'usuarios_verdade.csv'
        csv.write_text(CSV, encoding='utf-8')
        self.patches = [patch.object(pu, 'ARQUIVO_CSV', csv)]
        for p in self.patches:
            p.start()
        pu._base['mtime'] = None
        usuario_real.cache.limpar()
        self.maria = pu.definir_usuario(MARIA)['sessao_id']
        self.eduardo = pu.definir_usuario(EDUARDO)['sessao_id']

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.pasta.cleanup()
        usuario_real.cache.limpar()

    def servico(self, service):
        p = patch.object(views, 'get_service', lambda: service)
        p.start()
        self.addCleanup(p.stop)
        return service

    def modo(self, modo):
        from django.test import override_settings
        o = override_settings(CONVERSAS={'MODO': modo})
        o.enable()
        self.addCleanup(o.disable)

    def post(self, client, body, **extra):
        return client.post(URL, data=json.dumps(body), content_type='application/json', **extra)

    # ------------------------------------------------------------ sessão e CSRF

    def test_without_session_is_404_asking_for_definir(self):
        for resposta in (Client().get(BOOT), Client().get(BOOT + '?sessao_id=nao-existe'),
                         self.post(Client(), payload())):
            with self.subTest(status=resposta.status_code):
                self.assertEqual(resposta.status_code, 404)
                corpo = resposta.json()
                self.assertEqual((corpo['schema_version'], corpo['status']), ('1.0', 'unavailable'))
                self.assertIn('perfil-usuario/definir/', corpo['reply'])

    @unittest.expectedFailure
    def test_boot_nao_expoe_genero_nem_indice(self):
        """P0 2026-09-27: o 201 de definir/ já é {codigo, pessoa, nome_origem}, mas o GET de bootstrap de
        apps/conversas devolve o dict interno da sessão (com genero e indice). Defeito de produção em
        apps/conversas, fora do escopo da migração dos testes: xfail até o dono decidir. Vira 'unexpected
        success' quando o boot for corrigido; aí tira-se o decorador."""
        boot = Client().get(BOOT + '?sessao_id=' + self.maria)
        self.assertEqual(boot.status_code, 200)
        self.assertEqual(boot.json()['usuario'], {'codigo': MARIA, 'pessoa': 'Maria', 'nome_origem': 'nome_gerado'})
        self.assertNotIn('genero', boot.json()['usuario'])
        self.assertNotIn('indice', boot.json()['usuario'])

    def test_demo_cookie_csrf_and_contract_isolation(self):
        self.modo('demo')
        client = Client(enforce_csrf_checks=True)
        boot = client.get(BOOT + '?sessao_id=' + self.maria)
        self.assertEqual(boot.status_code, 200)
        self.assertEqual(boot.json()['mode'], 'demo')
        self.assertEqual((boot.json()['usuario']['codigo'], boot.json()['usuario']['pessoa']), (MARIA, 'Maria'))
        self.assertIn('csrftoken', client.cookies)
        self.assertIn(views.COOKIE, client.cookies)
        missing = self.post(client, payload())
        self.assertEqual((missing.status_code, missing.json()['status']), (403, 'unavailable'))
        headers = {'HTTP_X_CSRFTOKEN': client.cookies['csrftoken'].value, 'HTTP_ORIGIN': 'http://127.0.0.1:3000'}
        response = self.post(client, payload(), **headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn('não foi gerada por IA', response.json()['reply'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        other = Client()
        other.get(BOOT, HTTP_X_SESSAO_ID=self.eduardo)
        stolen = self.post(other, payload(cid=response.json()['conversation_id']))
        self.assertEqual(stolen.status_code, 404)

    def test_wrong_origin_is_rejected_by_csrf(self):
        self.modo('demo')
        client = Client(enforce_csrf_checks=True)
        client.get(BOOT + '?sessao_id=' + self.maria)
        r = self.post(client, payload(), HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value,
                      HTTP_ORIGIN='http://evil.example')
        self.assertEqual(r.status_code, 403)

    def test_header_session_works_on_post_without_bootstrap_cookie(self):
        self.modo('demo')
        r = self.post(Client(), payload(), HTTP_X_SESSAO_ID=self.maria)
        self.assertEqual(r.status_code, 200)

    def test_protocol_errors_have_only_released_envelope(self):
        self.modo('demo')
        for body in ['{invalid', '[]', '"hello"', '{"message":"' + 'x' * 17000 + '"}']:
            with self.subTest(body=body[:12]):
                client = Client()
                client.get(BOOT + '?sessao_id=' + self.maria)
                response = client.post(URL, data=body, content_type='application/json')
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['schema_version'], '1.0')
                self.assertNotIn('Traceback', response.content.decode())

    def test_other_methods_and_paths_stay_in_envelope(self):
        self.assertEqual(Client().get(URL).status_code, 405)
        self.assertEqual(Client().post(BOOT).status_code, 405)
        r = Client().get('/api/v1/context-agent/conversas/nao-existe/')
        self.assertEqual((r.status_code, r.json()['schema_version']), (404, '1.0'))

    def test_revoked_session_is_rechecked_even_for_identical_cached_payload(self):
        service = self.servico(ConversationService(gateway=FakeGateway(), context_builder=contexto_com(fonte_falsa)))
        client = Client()
        client.get(BOOT + '?sessao_id=' + self.maria)
        self.assertEqual(self.post(client, payload()).status_code, 200)
        pu._sessoes.pop(self.maria)
        self.assertEqual(self.post(client, payload()).status_code, 404)
        self.assertEqual(len(service.gateway.calls), 3)

    # ------------------------------------------------------------ números reais

    def test_spending_answer_uses_measured_fact_with_seal(self):
        gateway = GastoGateway()
        self.servico(ConversationService(gateway=gateway, context_builder=contexto_com(fonte_falsa)))
        client = Client()
        client.get(BOOT + '?sessao_id=' + self.maria)
        r = self.post(client, payload('quanto eu gasto por mês?'))
        self.assertEqual(r.status_code, 200)
        corpo = r.json()
        self.assertEqual(corpo['dados']['estado'], 'MEDIDO')
        self.assertEqual(corpo['dados']['selo']['fonte'], 'batalha-time-02-lxof.hackathon_dados.extrato_sintetico')
        contexto = gateway.calls[1][1]
        self.assertEqual({f['id']: f['value'] for f in contexto['facts']}['outflows'], '10790.43')

    def test_claim_with_value_other_than_measured_is_refused(self):
        """Prova negativa: o modelo não pode 'arredondar' nem inventar o valor medido."""
        self.servico(ConversationService(gateway=GastoGateway(valor='0.00'), context_builder=contexto_com(fonte_falsa)))
        client = Client()
        client.get(BOOT + '?sessao_id=' + self.maria)
        self.assertEqual(self.post(client, payload('quanto eu gasto por mês?')).status_code, 503)

    def test_real_usuario_real_path_with_fake_bigquery(self):
        gateway = FakeGateway()
        self.servico(ConversationService(gateway=gateway))
        with patch.object(usuario_real, '_novo_executor', ExecutorFalso):
            client = Client()
            client.get(BOOT + '?sessao_id=' + self.maria)
            r = self.post(client, payload('quanto eu gasto por mês?'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['dados']['estado'], 'MEDIDO')
        fatos = {f['id']: f['value'] for f in gateway.calls[1][1]['facts']}
        self.assertEqual((fatos['inflows'], fatos['outflows'], fatos['cash_flow']), ('5000.00', '4500.00', '500.00'))

    def test_broken_bigquery_is_nao_medido_without_numbers(self):
        """Prova negativa: BigQuery quebrado não produz fato nenhum, nem zero."""
        gateway = FakeGateway()
        self.servico(ConversationService(gateway=gateway))
        with patch.object(usuario_real, '_novo_executor', ExecutorQuebrado):
            client = Client()
            client.get(BOOT + '?sessao_id=' + self.maria)
            r = self.post(client, payload('quanto eu gasto por mês?'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['dados'], {'estado': 'NAO_MEDIDO', 'selo': None})
        self.assertEqual(gateway.calls[1][1]['facts'], [])

    # ------------------------------------------------------------ guard de identidade

    def _quem_sou_eu(self, reply, decision='allow', reasons=()):
        gateway = FakeGateway(reply)

        async def entrada(message, history):
            gateway.calls.append(('input', message, history))
            return {'decision': decision, 'reason_codes': list(reasons), 'constraints': [], 'policy_version': '1.0'}
        gateway.input_guard = entrada
        service = self.servico(ConversationService(gateway=gateway, context_builder=contexto_com(fonte_falsa)))
        client = Client()
        client.get(BOOT + '?sessao_id=' + self.maria)
        return self.post(client, payload('quem sou eu?')), service

    def test_identity_answer_with_name_and_code_is_released(self):
        reply = f'Você é Maria, código {MARIA}.'
        r, service = self._quem_sou_eu(reply)
        self.assertEqual((r.status_code, r.json()['reply']), (200, reply))
        self.assertIn({'event': 'identity_guard', 'estado': 'APROVADO'}, list(service.audit))

    def test_identity_answer_without_code_is_replaced_by_csv(self):
        """Prova negativa: resposta sem o código não sai; sai a do CSV."""
        r, service = self._quem_sou_eu('Você é Maria.')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Maria', r.json()['reply'])
        self.assertIn(MARIA, r.json()['reply'])
        self.assertIn({'event': 'identity_guard', 'estado': 'REPROVADO'}, list(service.audit))

    def test_identity_answer_with_wrong_person_is_replaced(self):
        """Prova negativa: o nome de outra pessoa não passa."""
        r, _ = self._quem_sou_eu(f'Você é Eduardo, código {EDUARDO}.')
        self.assertNotIn('Eduardo', r.json()['reply'])
        self.assertIn(MARIA, r.json()['reply'])

    def test_overcautious_input_guard_does_not_block_own_identity(self):
        r, _ = self._quem_sou_eu('não usado', decision='clarify')
        self.assertEqual(r.status_code, 200)
        self.assertIn(MARIA, r.json()['reply'])

    def test_privacy_denial_still_wins(self):
        r, _ = self._quem_sou_eu('não usado', decision='deny', reasons=['privacy'])
        self.assertEqual(r.json()['status'], 'safe_redirect')
        self.assertNotIn(MARIA, r.json()['reply'])


class PermitidosTest(unittest.TestCase):
    CODIGO_DIGITOS = '12345678-1234-4123-8123-123456789012'  # UUID válido com cara de cartão

    def test_titular_code_is_allowed(self):
        self.assertTrue(safe_text(f'Seu código é {MARIA}.', (MARIA,)))
        self.assertTrue(safe_text(f'Seu código é {self.CODIGO_DIGITOS}.', (self.CODIGO_DIGITOS,)))

    def test_digit_code_without_permission_is_refused(self):
        """Prova negativa: sem o titular, 16 dígitos seguidos por hífens continuam reprovados."""
        self.assertFalse(safe_text(f'Seu código é {self.CODIGO_DIGITOS}.'))

    def test_permission_does_not_release_other_numbers(self):
        """Prova negativa: o código permitido não libera outro 'cartão', CPF, nem valor que não é UUID."""
        self.assertFalse(safe_text(f'Seu código é {MARIA}; cartão 4111 1111 1111 1111.', (MARIA,)))
        self.assertFalse(safe_text(f'Seu código é {MARIA}; CPF 123.456.789-01.', (MARIA,)))
        self.assertFalse(safe_text('CPF 123.456.789-01', ('123.456.789-01',)))
        self.assertFalse(safe_text(f'Outro código {self.CODIGO_DIGITOS}.', (MARIA,)))


if __name__ == '__main__':
    unittest.main()
