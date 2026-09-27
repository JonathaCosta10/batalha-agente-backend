"""Caminho do compromisso de ponta a ponta pelo HTTP, com a forma de saída que o prompt pede ao Gemini (backend-22).

O Gemini real NÃO foi verificado (cota diária dos três modelos esgotada, medido 2026-09-27 12:29-12:31 BRT); este teste
fecha o que o teste anterior não cobria: categoria `delivery` (o resumo cita o gasto observado do grupo Delivery +
Restaurantes, com valor terminado em zero, "R$ 1.522,90" x fato "1522.9"), quatro turnos com a proposta referindo a
QUARTA fala, e o resto do caminho do front: proposta -> confirmar -> PATCH plano/ -> acompanhamento.
Guards e generate são dublês (FakeGateway); as validações determinísticas (trechos, números sem fonte, estado,
base do plano) são as reais.
"""
import json
import unittest

from conversas_apoio import FakeGateway, payload
from i_agora_apoio import MSG, ORIGEM, IAgoraBase, snapshot

from apps.conversas.service import ConversationService
from apps.i_agora import views

FALAS = ['Quero juntar dinheiro para uma viagem com a minha família no fim do ano.',
         'Tenho aluguel e a escola das crianças, isso eu não consigo cortar.',
         'Acho que consigo pedir menos delivery e cozinhar em casa nos dias de semana.',
         'Posso gastar no máximo R$ 900 por mês com delivery e refeições fora. Pode montar a proposta?']


class GatewayComoOPrompt(FakeGateway):
    """Só propõe o caso quando objetivo, contexto, ação e valor já foram ditos (quarta fala)."""
    def __init__(self, proposta):
        super().__init__()
        self.proposta = proposta

    async def generate(self, message, context, history, constraints, titular=None):
        self.calls.append(('generate', context, history.copy()))
        pronto = len(context['user_statements']) == 4
        return {'reply': 'Qual mudança parece viável para você?', 'status': 'needs_clarification',
                'capabilities': ['orcamento'], 'claims': [], 'missing_data': [],
                'commitment_proposal': dict(self.proposta, reference_month=context['financial_period']) if pronto else None}


PROPOSTA = {'objective': 'juntar dinheiro para uma viagem com a minha família',
            'personal_context': 'Tenho aluguel e a escola das crianças',
            'action': 'pedir menos delivery e cozinhar em casa nos dias de semana',
            'category': 'delivery', 'monthly_amount': 'R$ 900',
            'source_refs': {'objective': 1, 'personal_context': 2, 'action': 3, 'monthly_amount': 4}}


class CompromissoCaminhoCompleto(IAgoraBase):
    def setUp(self):
        super().setUp()
        original = self.src.load_ref

        def load_ref(ref):
            snap = original(ref)
            snap['categories'] = {'Delivery': '1200.40', 'Restaurantes': '322.50', 'Lojas e sites': '450.00'}
            snap['outflows'] = '3200.00'
            return snap
        self.src.load_ref = load_ref

    def conversar(self, proposta):
        self.service = ConversationService(gateway=GatewayComoOPrompt(proposta),
                                           principal_context_builder=views.conversation_context,
                                           on_commitment_proposed=views.offer_case)
        c = self.session(csrf=True)
        self.profile(c)
        tok = {'HTTP_X_CSRFTOKEN': c.cookies['csrftoken'].value, 'HTTP_ORIGIN': ORIGEM}
        cid, respostas = None, []
        for i, fala in enumerate(FALAS):
            r = c.post(MSG, json.dumps(payload(fala, f'm{i}', cid)), content_type='application/json', **tok)
            self.assertEqual(r.status_code, 200, r.content)
            cid = r.json()['conversation_id']
            respostas.append(r.json())
        return c, respostas

    def test_quatro_turnos_delivery_ate_acompanhamento(self):
        c, respostas = self.conversar(PROPOSTA)
        final = respostas[-1]
        self.assertIn('Pelo que conversamos', final['reply'])
        self.assertIn('R$ 1.522,90', final['reply'])  # grupo observado Delivery + Restaurantes, com o zero final
        self.assertIn('R$ 900,00', final['reply'])
        r = self.send(c, 'post', 'plano/proposta/', {'clientRequestId': 'b5a1e7c2-0f4e-4a57-9d8e-2f1b3c4d5e6f'})
        self.assertEqual(r.status_code, 200, r.content)
        s = r.json()['state']
        self.assertEqual((s['draft']['selected'], s['draft']['deliveryTarget'], s['stage']), (['delivery'], 900.0, 'confirm'))
        r = self.send(c, 'post', 'plano/confirmar/', {'version': s['version'], 'plan': s['draft'],
                                                      'clientRequestId': 'c0ffee00-1111-4222-8333-444455556666'})
        self.assertEqual(r.status_code, 201, r.content)
        v = r.json()['state']['version']
        r = self.send(c, 'patch', 'plano/', {'version': v, 'stage': 'card', 'phraseIndex': 0})
        self.assertEqual((r.status_code, r.json()['state']['stage']), (200, 'card'), r.content)
        r = c.get('/api/v1/context-agent/i-agora/acompanhamento/')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([(i['category'], i['status']) for i in r.json()['items']], [('delivery', 'NAO_MEDIDO')])

    def test_prova_negativa_valor_que_a_pessoa_nao_disse_nao_vira_caso(self):
        c, respostas = self.conversar({**PROPOSTA, 'monthly_amount': 'R$ 700'})
        self.assertNotIn('Pelo que conversamos', respostas[-1]['reply'])
        self.assertEqual(self.send(c, 'post', 'plano/proposta/', {'clientRequestId': 'p1'}).status_code, 409)

    def test_prova_negativa_alvo_acima_do_observado_nao_vira_caso(self):
        # Base com Delivery 600 e sem Restaurantes: R$ 900 não é redução; o caso não é preparado.
        self.src.load_ref = lambda ref: snapshot(ref)
        c, respostas = self.conversar(PROPOSTA)
        self.assertNotIn('Pelo que conversamos', respostas[-1]['reply'])
        self.assertEqual(self.send(c, 'post', 'plano/proposta/', {'clientRequestId': 'p2'}).status_code, 409)


if __name__ == '__main__':
    unittest.main()
