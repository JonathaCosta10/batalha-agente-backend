"""Estado explícito e contrato público de conversas/mensagens/ (apps/conversas/estado.py)."""
import unittest

from conversas_apoio import TITULAR, FakeGateway, contexto_com, fonte_falsa, fonte_quebrada, payload, run

from apps.conversas import estado
from apps.conversas.schemas import AgentDraftV1, Claim, ContratoRespostaV1
from apps.conversas.service import ConversationService


class GatewayCitando(FakeGateway):
    """Dublê que devolve um rascunho com claims fixas; nunca evidência de chamada ao Gemini."""

    def __init__(self, reply, claims=(), missing=(), status='ok'):
        super().__init__(reply)
        self.claims, self.missing, self.status = list(claims), list(missing), status

    async def generate(self, message, context, history, constraints, titular=None):
        self.calls.append(('generate', context, history.copy()))
        return {'reply': self.reply, 'status': self.status, 'capabilities': ['orcamento'], 'claims': self.claims,
                'missing_data': self.missing}


def servico(gateway, fonte=fonte_falsa):
    return ConversationService(gateway=gateway, context_builder=contexto_com(fonte))


SAIDAS = {'kind': 'financial', 'evidence_id': 'outflows', 'text': 'saídas médias', 'value': '10790.43'}


class Roteamento(unittest.TestCase):
    def test_analise_descritiva_com_fato_medido(self):
        gw = GatewayCitando('Pelo extrato, as saídas médias foram de R$ 10.790,43 por mês.', [SAIDAS])
        body, status = run(servico(gw).send('s', payload('Quanto eu gasto?'), titular=TITULAR))
        self.assertEqual((status, body['contrato']['estado']), (200, 'ANALISE_DESCRITIVA'))
        self.assertEqual(body['contrato']['evidence_ids'], ['outflows'])
        self.assertIsNotNone(body['contrato']['periodo'])
        ContratoRespostaV1.model_validate(body['contrato'])

    def test_prova_negativa_numero_sem_fonte_nao_sai(self):
        gw = GatewayCitando('Suas saídas foram de R$ 9.999,99 por mês.', [])
        body, status = run(servico(gw).send('s', payload('Quanto eu gasto?'), titular=TITULAR))
        self.assertEqual((status, body['contrato']['estado']), (503, 'INDISPONIVEL'))
        self.assertNotIn('9.999', body['reply'])
        self.assertEqual([c[0] for c in gw.calls], ['input', 'generate'])  # nem chega ao output_guard

    def test_prova_negativa_fato_do_extrato_sem_dados_medidos(self):
        # Com a fonte fora, o contexto não tem o fato: valid_evidence reprova; decidir() também reprovaria.
        gw = GatewayCitando('Pelo extrato, as saídas foram de R$ 10.790,43.', [SAIDAS])
        body, status = run(servico(gw, fonte_quebrada).send('s', payload('Quanto eu gasto?'), titular=TITULAR))
        self.assertEqual((status, body['contrato']['estado']), (503, 'INDISPONIVEL'))
        ctx = {'facts': [{'id': 'outflows', 'value': '10790.43', 'origin': 'bigquery_extrato'}]}
        draft = AgentDraftV1(reply='x', status='ok', capabilities=[], claims=[Claim(**SAIDAS)], missing_data=[])
        with self.assertRaises(estado.TransicaoInvalida):
            estado.decidir('rascunho', dados_estado='NAO_MEDIDO', draft=draft, context=ctx)

    def test_dados_insuficientes_quando_nao_medido(self):
        gw = GatewayCitando('Não consegui consultar seus dados agora. Posso explicar como montar um orçamento.',
                            missing=['dados_financeiros_do_titular'])
        body, status = run(servico(gw, fonte_quebrada).send('s', payload('Como estou?'), titular=TITULAR))
        self.assertEqual((status, body['contrato']['estado']), (200, 'DADOS_INSUFICIENTES'))
        self.assertIn('educacao_geral', body['contrato']['acoes_permitidas'])

    def test_educacao_geral_sem_fatos(self):
        body, status = run(servico(FakeGateway()).send('s', payload('O que é orçamento?'), titular=TITULAR))
        self.assertEqual((status, body['contrato']['estado']), (200, 'EDUCACAO_GERAL'))

    def test_extremo_vira_encaminhamento_sem_modelo(self):
        gw = FakeGateway()
        body, status = run(servico(gw).send('s', payload('quero me matar'), titular=TITULAR))
        self.assertEqual(body['contrato']['estado'], 'ENCAMINHAMENTO')
        self.assertEqual(gw.calls, [])

    def test_fallback_tem_estado_indisponivel_e_racional(self):
        body, _ = ConversationService().release(code='technical', http_status=503)
        self.assertEqual(body['contrato']['estado'], 'INDISPONIVEL')
        self.assertEqual(body['contrato']['acoes_permitidas'], [])
        self.assertEqual(set(body['contrato']['racional'][0]), {'observado', 'regra', 'consequencia'})


class Invariancia(unittest.TestCase):
    def test_parafrase_nao_muda_estado_nem_permissoes(self):
        vistos = set()
        for texto in ('Quanto eu gasto por mês?', 'me diz meus gastos mensais', 'QUAIS SÃO AS MINHAS SAÍDAS?'):
            gw = GatewayCitando('Pelo extrato, as saídas médias foram de R$ 10.790,43 por mês.', [SAIDAS])
            body, _ = run(servico(gw).send('s', payload(texto), titular=TITULAR))
            c = body['contrato']
            vistos.add((c['estado'], tuple(c['acoes_permitidas']), tuple(c['evidence_ids'])))
        self.assertEqual(len(vistos), 1)

    def test_trocar_valor_so_muda_o_indicador_dependente(self):
        from apps.conversas.context import build_context
        import copy
        from conversas_apoio import PERFIL
        outro = copy.deepcopy(PERFIL)
        outro['resumo']['outflow_mensal'] = 9000.00

        def fatos(perfil):
            return {f['id']: f['value'] for f in build_context(titular=TITULAR, fonte=lambda c: perfil)['facts']}
        a, b = fatos(PERFIL), fatos(outro)
        mudou = {k for k in a if a[k] != b.get(k)}
        self.assertEqual(mudou, {'outflows', 'cash_flow'})

    def test_trocar_titular_nao_reusa_evidencia(self):
        from conversas_apoio import EDUARDO
        vistos = []

        def fonte(codigo):
            vistos.append(codigo)
            return fonte_falsa(codigo)
        service = servico(GatewayCitando('ok'), fonte)
        run(service.send('s1', payload('oi', 'm1'), titular=TITULAR))
        eduardo = {'codigo': EDUARDO, 'pessoa': 'Eduardo', 'genero': 'M', 'indice': 2}
        with self.assertRaises(AssertionError):  # fonte_falsa só conhece Maria: prova que consultou o novo código
            fonte(EDUARDO)
        body, status = run(service.send('s2', payload('oi', 'm2'), titular=eduardo))
        self.assertEqual(status, 200)
        self.assertEqual(body['dados']['estado'], 'NAO_MEDIDO')  # não herdou os números de Maria
        self.assertEqual(vistos[0], TITULAR['codigo'])


if __name__ == '__main__':
    unittest.main()
