"""Rotas i-agora pelo test client, com CSRF ligado, como o front (Frontend/src/services/backend.ts).

Portado de Frontend/agent_backend/tests/test_integrated_planning.py e test_natural_dialogue.py (2026-09-27).
Inclui: o conflito de i-agora/plano/proposta/ (contrato do front x contrato antigo PlanoPropostaAPI), o caso de
compromisso vindo da conversa (FakeGateway, nunca Gemini) e a fonte do extrato com executor falso.
"""
import asyncio
import json
import unittest
from unittest.mock import patch

from conversas_apoio import FakeGateway, payload
from i_agora_apoio import MSG, ORIGEM, REFS, ROOT, IAgoraBase

from django.test import Client

from apps.conversas.service import ConversationService
from apps.i_agora import views
from apps.i_agora.fonte import FonteExtrato, SourceUnavailable
from apps.i_agora.store import PlanStore

CASE = {'objective': 'organizar meus gastos', 'personal_context': 'preservar despesas essenciais',
        'action': 'cozinhar em casa nos dias úteis', 'category': 'delivery', 'monthly_amount': '350.00',
        'reference_month': '2025-11'}


class IAgoraHttpTest(IAgoraBase):
    def test_without_session_is_401(self):
        self.assertEqual(Client().get(ROOT + 'plano/').status_code, 401)
        self.assertEqual(Client().get(ROOT + 'perfil/').json()['codigo'], 'auth')

    def test_http_full_goal_csrf_idempotency_and_isolation(self):
        c = self.session(csrf=True)
        s = c.get(ROOT + 'perfil/').json()['state']
        self.assertNotIn('snapshot', s)
        self.assertTrue(s['opening']['message'])
        # Preparação confiável do servidor depois do diálogo; o cliente HTTP não consegue criar este caso.
        s = PlanStore().prepare_case(self.owner(c), s['version'], s['planId'], CASE)
        body = json.dumps({'version': s['version'], 'plan': s['draft'], 'clientRequestId': 'c1'})
        url = ROOT + 'plano/confirmar/'
        self.assertEqual(c.post(url, body, content_type='application/json').status_code, 403)  # sem token
        tok = c.cookies['csrftoken'].value
        self.assertEqual(c.post(url, body, content_type='application/json', HTTP_X_CSRFTOKEN=tok,
                                HTTP_ORIGIN='https://evil.example').status_code, 403)
        r = c.post(url, body, content_type='application/json', HTTP_X_CSRFTOKEN=tok, HTTP_ORIGIN=ORIGEM)
        self.assertEqual(r.status_code, 201, r.content)
        r = c.post(url, body, content_type='application/json', HTTP_X_CSRFTOKEN=tok, HTTP_ORIGIN=ORIGEM)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['replayed'])
        self.assertIsNone(c.get(ROOT + 'acompanhamento/').json()['items'][0]['spent'])
        self.assertEqual(c.get(ROOT + 'plano/').json()['state']['confirmed'], s['draft'])
        r = self.send(c, 'patch', 'plano/', {'version': r.json()['state']['version'], 'stage': 'finish', 'phraseIndex': 1})
        self.assertEqual((r.status_code, r.json()['state']['stage']), (200, 'finish'))
        other = self.session()
        self.assertIsNone(other.get(ROOT + 'plano/').json()['state'])

    def test_open_and_proposal_shortcut_never_create_case(self):
        c = self.session(csrf=True)
        self.profile(c)
        r = self.send(c, 'post', 'plano/proposta/', {'clientRequestId': 'p1'})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()['codigo'], 'stale')
        state = c.get(ROOT + 'plano/').json()['state']
        self.assertEqual(state['stage'], 'intro')
        self.assertFalse(state.get('commitmentCase'))
        self.assertIsNone(state['confirmed'])

    def test_confirm_requires_case_not_just_numbers(self):
        c = self.session(csrf=True)
        s = self.profile(c)[1]['state']
        r = self.send(c, 'post', 'plano/confirmar/', {'version': s['version'], 'clientRequestId': 'bypass',
                                                      'plan': {**s['draft'], 'shoppingTarget': 200, 'selected': ['shopping']}})
        self.assertEqual(r.status_code, 409)
        self.assertIsNone(c.get(ROOT + 'plano/').json()['state']['confirmed'])

    def test_proposal_post_returns_case_and_delete_withdraws_it(self):
        c = self.session(csrf=True)
        s = self.profile(c)[1]['state']
        PlanStore().prepare_case(self.owner(c), s['version'], s['planId'], CASE)
        r = self.send(c, 'post', 'plano/proposta/', {'clientRequestId': 'p1'})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['state']['commitmentCase']['objective'], CASE['objective'])
        self.assertEqual(r.json()['basis']['rule'], 'conversation_grounded_case')
        r = self.send(c, 'delete', 'plano/proposta/')
        self.assertEqual((r.status_code, r.json()['state']['stage']), (200, 'invite'))
        self.assertNotIn('commitmentCase', r.json()['state'])
        self.assertEqual(self.send(c, 'patch', 'plano/rascunho/', {}).status_code, 409)

    def test_proposal_new_contract_requires_csrf(self):
        c = self.session(csrf=True)
        self.profile(c)
        r = c.post(ROOT + 'plano/proposta/', json.dumps({'clientRequestId': 'p1'}), content_type='application/json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(c.delete(ROOT + 'plano/proposta/').status_code, 403)

    def test_proposal_old_contract_still_served_by_plano_proposta_api(self):
        """Contrato anterior da mesma URL (docs/contrato-api-frontend.md §4.7): sem clientRequestId vai para
        PlanoPropostaAPI, sem sessão nem CSRF. Sem ref: 400, como antes."""
        self.assertEqual(Client().post(ROOT + 'plano/proposta/', {}, content_type='application/json').status_code, 400)
        self.assertEqual(Client().get(ROOT + 'plano/proposta/').status_code, 400)
        with patch('apps.context_agent_datadriven.services.plano_proposta.proposta',
                   lambda ref, data_corte=None: {'ref': ref, 'estado': 'OK'}):
            r = Client(enforce_csrf_checks=True).post(ROOT + 'plano/proposta/', {'ref': REFS[0]},
                                                      content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['ref'], REFS[0])

    def test_source_failure_is_structured_503_never_generic_profile(self):
        self.src.fail = 1
        r = self.session().get(ROOT + 'perfil/')
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()['erro'], 'perfil_indisponivel')
        self.assertTrue(r.json()['motivo'])
        self.assertNotIn('person', r.json())

    def test_reset_keeps_client_and_clears_plan(self):
        c = self.session(csrf=True)
        s = self.profile(c)[1]['state']
        PlanStore().prepare_case(self.owner(c), s['version'], s['planId'], CASE)
        r = self.send(c, 'delete', 'plano/')
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()['state'].get('commitmentCase'))
        self.assertEqual(r.json()['state']['profile']['person']['idUsuario'], s['profile']['person']['idUsuario'])


class CommitmentGateway(FakeGateway):
    """Segundo turno: o 'modelo' propõe o caso com trechos das falas; o servidor valida e grava."""
    case = {'objective': 'viajar sem apertar o orçamento', 'personal_context': 'preservar o aluguel',
            'action': 'esperar dois dias antes de comprar', 'category': 'shopping', 'monthly_amount': 'R$ 200,00',
            'reference_month': '2025-11'}

    async def generate(self, message, context, history, constraints, titular=None):
        self.calls.append(('generate', context, history.copy()))
        proposta = {**self.case, 'source_refs': {'objective': 1, 'personal_context': 1, 'action': 2, 'monthly_amount': 2}}
        return {'reply': 'Qual mudança é viável?', 'status': 'ok', 'capabilities': ['orcamento'], 'claims': [],
                'missing_data': [], 'commitment_proposal': proposta if history else None}


class ConversationCommitmentTest(IAgoraBase):
    def test_case_only_released_after_dialogue_then_panel_confirms(self):
        self.service = ConversationService(gateway=CommitmentGateway(), principal_context_builder=views.conversation_context,
                                           on_commitment_proposed=views.offer_case)
        c = self.session(csrf=True)
        self.profile(c)
        tok = {'HTTP_X_CSRFTOKEN': c.cookies['csrftoken'].value, 'HTTP_ORIGIN': ORIGEM}
        r = c.post(MSG, json.dumps(payload('Quero viajar sem apertar o orçamento e preservar o aluguel.')),
                   content_type='application/json', **tok)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(c.get(ROOT + 'plano/').json()['state'].get('commitmentCase'))
        r = c.post(MSG, json.dumps(payload('Vou esperar dois dias antes de comprar. Meta mensal de R$ 200,00 em lojas e sites.',
                                           'm2', r.json()['conversation_id'])), content_type='application/json', **tok)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn('Pelo que conversamos', r.json()['reply'])
        # Contexto da conversa recebeu o plano do dono (fatos BQ:* e goal_state).
        ctx = [x[1] for x in self.service.gateway.calls if x[0] == 'generate'][-1]
        self.assertIn('BQ:category:Delivery', {f['id'] for f in ctx['facts']})
        self.assertEqual(ctx['financial_period'], '2025-11')
        r = self.send(c, 'post', 'plano/proposta/', {'clientRequestId': 'p1'})
        self.assertEqual(r.status_code, 200, r.content)
        s = r.json()['state']
        self.assertEqual((s['commitmentCase']['objective'], s['draft']['shoppingTarget']), (self.service.gateway.case['objective'], 200))
        r = self.send(c, 'post', 'plano/confirmar/', {'version': s['version'], 'plan': s['draft'], 'clientRequestId': 'ok1'})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['state']['confirmed']['selected'], ['shopping'])

    def test_projection_does_not_prepare_commitment_and_forget_clears(self):
        class Gateway(FakeGateway):
            async def generate(self, *args, **kwargs):
                return {'reply': 'Vamos conferir os dados?', 'status': 'ok', 'capabilities': ['orcamento'], 'claims': [],
                        'missing_data': [], 'projection_proposal': {'objective': 'reduzir delivery', 'category': 'delivery',
                                                                     'current_spending': '600', 'target_spending': '350',
                                                                     'reference_month': '2025-11'}}
        calls = []
        service = ConversationService(gateway=Gateway(), on_commitment_proposed=lambda *a: calls.append(a))
        r, status = asyncio.run(service.send('a', payload('Quero reduzir delivery de 600 para 350 por mês, referência 2025-11.')))
        self.assertEqual(status, 200)
        self.assertFalse(calls)
        self.assertTrue(service.proposals)
        service.forget('a')
        self.assertFalse(service.proposals or service.sessions or service.cache)
        self.assertEqual(asyncio.run(service.send('a', payload('Sim, confirmo', 'other', r['conversation_id'])))[1], 404)


class FonteExtratoTest(unittest.TestCase):
    class Executor:
        def __init__(self, rows=None, erro=None):
            self.rows, self.erro, self.seen = rows, erro, []

        def executar(self, sql, params):
            self.seen.append((sql, params))
            if self.erro:
                raise self.erro
            self.ultimo_job = {'job_id': 'job-x', 'bytes_processados': 10}
            return self.rows

    def fonte(self, executor):
        f = FonteExtrato(executor_factory=lambda: executor)
        f.customers = lambda: REFS[:2]
        return f

    def test_load_ref_queries_by_id_usuario_as_parameter(self):
        ex = self.Executor([{'period': '2025-11', 'category': 'Delivery', 'inflows': '10', 'outflows': '5', 'invalid': 0},
                            {'period': '2025-11', 'category': 'Lojas e sites', 'inflows': '0', 'outflows': '7.5', 'invalid': 0}])
        snap = self.fonte(ex).load_ref(REFS[1])
        self.assertEqual(set(snap), {'client_ref', 'index', 'reference_month', 'inflows', 'outflows', 'categories', 'seal'})
        self.assertEqual((snap['client_ref'], snap['index'], snap['outflows']), (REFS[1], 2, '12.50'))
        sql, params = ex.seen[0]
        self.assertEqual(params['customer'], REFS[1])
        self.assertIn('@customer', sql)
        self.assertNotIn(REFS[1], sql)  # parâmetro nomeado, nunca interpolado

    def test_failures_are_source_unavailable_never_fixture(self):
        with self.assertRaises(SourceUnavailable):
            self.fonte(self.Executor(erro=ConnectionError('sem ADC'))).load_ref(REFS[0])
        with self.assertRaises(SourceUnavailable):
            self.fonte(self.Executor([])).load_ref(REFS[0])
        with self.assertRaises(SourceUnavailable):
            self.fonte(self.Executor([{'period': '2025-11', 'category': 'X', 'inflows': '1', 'outflows': '1',
                                       'invalid': 3}])).load_ref(REFS[0])
        with self.assertRaises(SourceUnavailable):
            self.fonte(self.Executor([])).load_ref('fora-do-catalogo')


if __name__ == '__main__':
    unittest.main()
