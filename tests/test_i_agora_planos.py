"""Plano i-agora: domínio, store e validação do caso de compromisso, sem HTTP.

Portado de Frontend/agent_backend/tests/test_plans.py e test_natural_dialogue.py (2026-09-27). Os testes do
GCSPlanStore e do orçamento diário persistente (admit_call) não foram portados: essas peças não vieram para
este backend (o plano vive no banco do Django; o teto de chamadas é CONVERSAS['MAX_CHAMADAS']).
"""
import unittest

from i_agora_apoio import IAgoraBase, snapshot

from apps.conversas.commitments import validate_case
from apps.i_agora.domain import draft_for_case, from_snapshot, validate_plan
from apps.i_agora.store import Conflict, PlanStore


class PlanStoreTest(IAgoraBase):
    def test_plan_confirmation_persists_replays_and_isolates(self):
        store = PlanStore()
        state = store.open('owner-a', from_snapshot(snapshot()))
        self.assertIsNone(state['confirmed'])
        plan = {**state['draft'], 'deliveryTarget': 350, 'selected': ['delivery']}
        confirmed = store.confirm('owner-a', 'request1', state['version'], plan)
        self.assertEqual(confirmed['state']['confirmed']['deliveryTarget'], 350)
        self.assertEqual(confirmed['state']['totals']['released'], 250)
        self.assertEqual(confirmed['state']['totals']['initial'], -200)
        self.assertEqual(PlanStore().get('owner-a')['confirmed'], plan)
        self.assertIsNone(store.get('other-owner'))
        self.assertIs(store.confirm('owner-a', 'request1', state['version'], plan)['replayed'], True)
        with self.assertRaises(Conflict):
            store.confirm('owner-a', 'request1', state['version'], {**plan, 'deliveryTarget': 300})

    def test_confirm_rejects_client_change_of_observed_baseline(self):
        store = PlanStore()
        s = store.open('a', from_snapshot(snapshot()))
        with self.assertRaises(ValueError):
            store.confirm('a', 'r', s['version'], {**s['draft'], 'income': 99999, 'selected': ['delivery']})

    def test_consent_is_separate_from_projection(self):
        store = PlanStore()
        s = store.open('a', from_snapshot(snapshot()))
        changed = store.adjust('a', s['version'], {'deliveryTarget': 350, 'selected': ['delivery']})
        self.assertEqual((changed['stage'], changed['confirmed']), ('confirm', None))

    def test_stale_version_is_conflict(self):
        store = PlanStore()
        s = store.open('a', from_snapshot(snapshot()))
        with self.assertRaises(Conflict):
            store.adjust('a', s['version'] + 7, {'deliveryTarget': 350, 'selected': ['delivery']})

    def test_case_grounded_in_iterative_dialogue_and_source(self):
        proposal = {'objective': 'viajar sem apertar meu orçamento', 'personal_context': 'preciso preservar o dinheiro do aluguel',
                    'action': 'vou esperar dois dias antes de comprar', 'category': 'shopping', 'monthly_amount': 'R$ 200,00',
                    'reference_month': '2025-11'}
        messages = ['Quero viajar sem apertar meu orçamento, preciso preservar o dinheiro do aluguel.',
                    'Nas lojas e sites vou esperar dois dias antes de comprar. Quero limitar a R$ 200,00 por mês.']
        with self.assertRaises(ValueError):
            validate_case(proposal, messages[:1], '2025-11')
        with self.assertRaises(ValueError):
            validate_case({**proposal, 'personal_context': 'contexto inventado'}, messages, '2025-11')
        case = validate_case(proposal, messages, '2025-11')
        store = PlanStore()
        s = store.open('a', from_snapshot(snapshot()))
        prepared = store.prepare_case('a', s['version'], s['planId'], case)
        self.assertEqual(prepared['commitmentCase']['objective'], proposal['objective'])
        self.assertEqual(prepared['draft']['shoppingTarget'], 200)
        self.assertEqual((prepared['stage'], prepared['confirmed']), ('confirm', None))
        self.assertIsNone(store.reset('a').get('commitmentCase'))


class DomainTest(unittest.TestCase):
    def test_segmentation_is_explicit_situation_not_gender_or_credit(self):
        result = from_snapshot(snapshot())
        self.assertEqual(result['profile']['situation'], 'fluxo_negativo')
        self.assertIsNone(result['profile']['arrears'])
        self.assertIsNone(result['profile']['person']['genero'])
        self.assertEqual(result['profile']['referencePeriod']['anomes'], 202511)
        self.assertEqual(result['profile']['planPeriod']['anomes'], 202512)
        self.assertEqual(result['draft']['selected'], [])
        self.assertEqual(result['draft']['deliveryTarget'], 600)  # nenhuma redução imposta

    def test_invalid_money_cannot_be_saved(self):
        for value in (-1, float('nan'), float('inf'), 1.234):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_plan({'deliveryTarget': value})

    def test_reduction_target_must_be_below_observed(self):
        base = from_snapshot(snapshot())['draft']
        with self.assertRaises(ValueError):
            draft_for_case(base, {'category': 'delivery', 'monthly_amount': '600.00'})
        self.assertEqual(draft_for_case(base, {'category': 'delivery', 'monthly_amount': '350.00'})['deliveryTarget'], 350)

    def test_source_refs_preserve_actual_words_instead_of_model_paraphrase(self):
        messages = ['Quero viajar sem comprometer o aluguel e minhas contas essenciais.',
                    'Tenho o hábito de comprar sem pensar; posso esperar dois dias antes de comprar.',
                    'Quero limitar a R$ 600,00 por mês.']
        proposal = {'objective': messages[0], 'personal_context': 'Tenho o hábito de comprar sem pensar em lojas e sites.',
                    'action': 'posso esperar dois dias antes de comprar.', 'category': 'shopping', 'monthly_amount': '600,00',
                    'reference_month': '2025-12',
                    'source_refs': {'objective': 1, 'personal_context': 2, 'action': 2, 'monthly_amount': 3}}
        result = validate_case(proposal, messages, '2025-12')
        self.assertEqual(result['personal_context'], 'Tenho o hábito de comprar sem pensar')
        self.assertEqual(result['action'], proposal['action'])
        with self.assertRaises(ValueError):
            validate_case({**proposal, 'monthly_amount': '900,00'}, messages, '2025-12')

    def test_adjustment_does_not_copy_old_amount_into_action(self):
        messages = ['Quero viajar sem comprometer o aluguel.', 'Preciso preservar minhas contas essenciais.',
                    'Um limite de R$ 600,00 cabe na rotina. Pode preparar a proposta com a espera de dois dias antes das compras.',
                    'Prefiro um limite de R$ 550,00 por mês.']
        proposal = {'objective': 'Quero viajar sem comprometer o aluguel.',
                    'personal_context': 'Preciso preservar minhas contas essenciais.',
                    'action': 'esperar dois dias antes de comprar.', 'category': 'shopping', 'monthly_amount': '550,00',
                    'reference_month': '2025-12',
                    'source_refs': {'objective': 1, 'personal_context': 2, 'action': 3, 'monthly_amount': 4}}
        result = validate_case(proposal, messages, '2025-12')
        self.assertNotIn('600', result['action'])
        self.assertIn(result['action'], messages[2])
        self.assertEqual(result['monthly_amount'], '550.00')


if __name__ == '__main__':
    unittest.main()
