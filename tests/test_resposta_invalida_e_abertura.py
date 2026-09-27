"""Erro real do dono, 2026-09-27 13:09 BRT (:3000 -> :8000): abertura -> "São gastos que costumam se repetir, quase
toda semana." -> 503 provedor_indisponivel/NAO_CLASSIFICADO em 16,4 s.

Causa medida às 13:15 BRT (Gemini real, gemini-3.1-flash-lite): `maxOutputTokens` inclui o pensamento; o output_guard
pensou 490 tokens no teto de 512 e devolveu finishReason MAX_TOKENS com o JSON cortado ('{"decision": "release",').
O router parava na 1ª falha sem status. E a pergunta da abertura não chegava ao modelo (history vazio).

Cobre: RespostaInvalida (MAX_TOKENS, JSON, schema) segue para o próximo modelo da ordem sem gastar a nova chamada da
política; prazo do turno corta a tentativa que não cabe; tipo `resposta_modelo_invalida` com a linha 503 (nunca
NAO_CLASSIFICADO); status com todas as etapas; tetos de saída; abertura no contexto da conversa.
Nada chama rede.
"""
import json
import time
import unittest

import conversas_apoio  # noqa: F401  (django.setup)
from conversas_apoio import FakeGateway, payload, run
from i_agora_apoio import MSG, ORIGEM, IAgoraBase

from apps.conversas import gateway as gw_mod
from apps.conversas import roteador as rt
from apps.conversas.gateway import ErroProvedor, GeminiGateway, RespostaInvalida
from apps.conversas.service import ConversationService
from apps.i_agora import views as i_views
from desafio_itau.politica import erros_api

GEN = rt.carregar().router.etapas['generate']
G = rt.carregar().router.etapas['output_guard']
CORTADO = {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': '{"decision": "release",'}]}}],
           'usageMetadata': {'promptTokenCount': 7670, 'candidatesTokenCount': 6, 'thoughtsTokenCount': 490},
           'modelVersion': 'gemini-3.1-flash-lite'}


def guard_ok(modelo):
    return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text':
            '{"decision":"release","reason_codes":[],"constraints":[],"policy_version":"1.0"}'}]}}],
            'modelVersion': modelo}


class Relogio:
    t = 100.0

    def __call__(self):
        return self.t


def gateway(respostas):
    """respostas: {modelo: dict de resposta | exceção}; ausentes respondem o guard válido."""
    chamadas, corpos = [], []

    def transporte(modelo, corpo):
        chamadas.append(modelo)
        corpos.append(corpo)
        r = respostas.get(modelo)
        if isinstance(r, Exception):
            raise r
        return r or guard_ok(modelo)
    return GeminiGateway(transporte=transporte, roteador=rt.Roteador(relogio=Relogio())), chamadas, corpos


def guard(g):
    return run(g.output_guard('oi', {'reply': 'x'}, {'reference_date': '2026-09-27'}))


class RespostaInvalidaSegueAOrdem(unittest.TestCase):
    def test_max_tokens_segue_para_o_proximo_modelo(self):
        g, chamadas, _ = gateway({G[0]: CORTADO})
        self.assertEqual(guard(g)['decision'], 'release')
        self.assertEqual(chamadas, [G[0], G[1]])
        m = [x for x in g.metrics if x['outcome'] == 'failed_or_uncertain'][0]
        self.assertEqual((m['error_type'], m['motivo_invalida'], m['output_tokens']), ('RespostaInvalida', 'MAX_TOKENS', 6))

    def test_caso_do_dono_429_mais_invalida_ainda_chega_ao_terceiro(self):
        """generate: principal 429 (usa a nova chamada da política) -> reserva cortado -> terceiro responde."""
        g, chamadas, _ = gateway({G[0]: ErroProvedor(429, 'dia'), G[1]: CORTADO})
        self.assertEqual(guard(g)['decision'], 'release')
        self.assertEqual(chamadas, G[:3])
        self.assertEqual(g.calls, 3)

    def test_json_e_schema_invalidos_tambem_seguem(self):
        for texto in ('nao json', '{"decision":"talvez","reason_codes":[],"constraints":[],"policy_version":"1.0"}'):
            with self.subTest(texto=texto):
                ruim = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': texto}]}}]}
                g, chamadas, _ = gateway({G[0]: ruim})
                guard(g)
                self.assertEqual(chamadas, [G[0], G[1]])

    def test_timeout_depois_429_do_dia_ainda_tenta_o_seguinte(self):
        """:8013 13:20: guard 3.1-flash-lite timeout -> o mais rápido (3.5-flash-lite) 429 dia -> antes parava ali."""
        g, chamadas, _ = gateway({G[0]: TimeoutError(), 'gemini-3.5-flash-lite': ErroProvedor(429, 'dia')})
        self.assertEqual(guard(g)['decision'], 'release')
        self.assertEqual(chamadas, [G[0], 'gemini-3.5-flash-lite', 'gemini-3.6-flash'])

    def test_429_por_minuto_depois_de_timeout_segue_a_ordem(self):
        """erros_api 1.4.0 ('ordem_no_prazo'): antes parava na 2ª chamada; agora segue ao próximo não tentado."""
        g, chamadas, _ = gateway({G[0]: TimeoutError(), 'gemini-3.5-flash-lite': ErroProvedor(429, 'minuto', 20)})
        self.assertEqual(guard(g)['decision'], 'release')
        self.assertEqual(chamadas, [G[0], 'gemini-3.5-flash-lite', 'gemini-3.6-flash'])

    def test_prova_negativa_503_em_todos_cada_modelo_uma_vez_e_sai_503(self):
        g, chamadas, _ = gateway({m: ErroProvedor(503) for m in G})
        with self.assertRaises(ErroProvedor) as ctx:
            guard(g)
        self.assertEqual(ctx.exception.code, 503)
        self.assertEqual(sorted(chamadas), sorted(G))   # todos tentados, nenhum repetido

    def test_prova_negativa_400_nao_troca(self):
        g, chamadas, _ = gateway({G[0]: ErroProvedor(400)})
        with self.assertRaises(ErroProvedor):
            guard(g)
        self.assertEqual(chamadas, [G[0]])

    def test_todos_invalidos_sai_resposta_invalida_sem_repetir_modelo(self):
        g, chamadas, _ = gateway({m: CORTADO for m in G})
        with self.assertRaises(RespostaInvalida):
            guard(g)
        self.assertEqual(chamadas, list(G))   # cada modelo uma vez, nunca o mesmo pedido ao mesmo modelo

    def test_prazo_do_turno_corta_a_tentativa_que_nao_cabe(self):
        g, chamadas, _ = gateway({G[0]: CORTADO})
        token = gw_mod.PRAZO_TURNO.set(time.monotonic() + 3)   # guard tem timeout de 10 s: não cabe
        try:
            with self.assertRaises(RespostaInvalida):
                guard(g)
        finally:
            gw_mod.PRAZO_TURNO.reset(token)
        self.assertEqual(chamadas, [G[0]])

    def test_tetos_de_saida_cobrem_o_pensamento(self):
        g, _, corpos = gateway({})
        guard(g)
        self.assertEqual(corpos[0]['generationConfig']['maxOutputTokens'], gw_mod.MAX_TOKENS_GUARD)
        self.assertGreaterEqual(gw_mod.MAX_TOKENS_GUARD, 4 * 490)      # 490 de pensamento medidos cortaram 512
        self.assertGreaterEqual(gw_mod.MAX_TOKENS_GENERATE, 2 * (1026 + 260))


class StatusMostraTodasAsEtapas(unittest.TestCase):
    def test_etapa_que_so_falhou_aparece_com_o_resultado(self):
        g, _, _ = gateway({m: CORTADO for m in G})
        with self.assertRaises(RespostaInvalida):
            guard(g)
        e = g.roteador.estado()
        self.assertEqual(set(e['ultimo_modelo_por_etapa']), set(rt.ETAPAS))
        self.assertIsNone(e['ultimo_modelo_por_etapa']['output_guard'])
        self.assertEqual(e['ultima_tentativa_por_etapa']['output_guard'],
                         {'modelo': G[-1], 'resultado': 'resposta_invalida:MAX_TOKENS'})
        self.assertEqual(e['proximo_por_etapa']['generate'], GEN[0])


class EnvelopeDoFront(unittest.TestCase):
    def test_todos_invalidos_http_503_tipo_proprio_nunca_nao_classificado(self):
        class Cortado(FakeGateway):
            async def generate(self, *a, **k):
                raise RespostaInvalida('MAX_TOKENS')
        corpo, status = run(ConversationService(gateway=Cortado()).send('a', payload()))
        e = corpo['erro_api']
        self.assertEqual((status, e['tipo'], e['codigo'], e['nome']),
                         (503, 'resposta_modelo_invalida', 503, 'ServiceUnavailable'))
        self.assertEqual(e['acao_cliente'], 'aguardar_ou_encaminhar')

    def test_prova_negativa_excecao_sem_status_generica_continua_nao_classificada(self):
        class Quebrado(FakeGateway):
            async def generate(self, *a, **k):
                raise RuntimeError('x')
        corpo, _ = run(ConversationService(gateway=Quebrado()).send('a', payload()))
        self.assertEqual((corpo['erro_api']['tipo'], corpo['erro_api']['nome']), ('provedor_indisponivel', 'NAO_CLASSIFICADO'))

    def test_politica_1_4_0(self):
        pol = erros_api.carregar()
        self.assertEqual(pol.versao, '1.4.0')
        self.assertEqual(pol.limites.troca_de_modelo_no_turno, 'ordem_no_prazo')
        self.assertEqual(erros_api.http_de('resposta_modelo_invalida'), 503)
        self.assertTrue(all(not t.repetir_mesmo_pedido for t in pol.erros.values()))
        self.assertEqual(pol.limites.novas_chamadas_max, 1)


class ValorCitadoContraOFato(unittest.TestCase):
    """Medido 13:30 BRT: claim "34.60" x fato BQ:group_delivery_restaurants "34.6" (str de float) -> 503 indevido."""

    def draft(self, valor):
        from apps.conversas.schemas import AgentDraftV1
        return AgentDraftV1.model_validate_json(json.dumps({
            'reply': 'Esses gastos se repetem.', 'status': 'needs_clarification', 'capabilities': ['orcamento'],
            'claims': [{'kind': 'financial', 'evidence_id': 'BQ:g', 'text': 'grupo', 'value': valor}],
            'missing_data': [], 'projection_proposal': None, 'commitment_proposal': None}))

    def test_mesmo_numero_com_zero_final_passa(self):
        from apps.conversas.rules import valid_evidence
        ctx = {'facts': [{'id': 'BQ:g', 'value': '34.6'}]}
        for v in ('34.60', '34.6', '34.600'):
            with self.subTest(v=v):
                self.assertTrue(valid_evidence(self.draft(v), ctx))

    def test_prova_negativa_numero_diferente_ou_formato_livre_reprova(self):
        from apps.conversas.rules import valid_evidence
        ctx = {'facts': [{'id': 'BQ:g', 'value': '34.6'}]}
        for v in ('34.61', '34', '346', 'R$ 34,60', '34,60', '3.46e1', ' 34.6'):
            with self.subTest(v=v):
                self.assertFalse(valid_evidence(self.draft(v), ctx))
        self.assertFalse(valid_evidence(self.draft('2025-12'), {'facts': [{'id': 'BQ:g', 'value': '2025-12-01'}]}))


class AberturaNoContexto(IAgoraBase):
    def test_primeira_resposta_chega_ao_modelo_com_a_pergunta_da_abertura(self):
        vistos = []

        class Espiao(FakeGateway):
            async def generate(self, message, context, history, constraints, titular=None):
                vistos.append((message, context.get('abertura'), list(history)))
                return await super().generate(message, context, history, constraints, titular)
        self.service = ConversationService(gateway=Espiao(), principal_context_builder=i_views.conversation_context,
                                           on_commitment_proposed=i_views.offer_case)
        c = self.session(csrf=True)
        self.profile(c)
        r = self.send(c, 'post', 'sessao/abertura/', {'origem': 'fab'})
        self.assertEqual(r.status_code, 201, r.content)
        abertura = r.json()['state']['opening']
        tok = {'HTTP_X_CSRFTOKEN': c.cookies['csrftoken'].value, 'HTTP_ORIGIN': ORIGEM}
        fala = 'São gastos que costumam se repetir, quase toda semana.'
        r = c.post(MSG, json.dumps(payload(fala, 'm1')), content_type='application/json', **tok)
        self.assertEqual(r.status_code, 200, r.content)
        mensagem, ctx, historico = vistos[0]
        self.assertEqual((mensagem, historico), (fala, []))
        self.assertEqual(ctx['foco'], abertura['focus'])
        self.assertTrue(abertura['message'].endswith(ctx['pergunta']))
        self.assertIn('?', ctx['pergunta'])
        self.assertNotIn('\n', ctx['pergunta'])

    def test_prompt_manda_seguir_o_fio_da_abertura(self):
        from apps.conversas.prompts.renderer import render_prompt
        texto, _ = render_prompt('system', reference_date='2026-09-27')
        self.assertIn('context.abertura.pergunta', texto)


if __name__ == '__main__':
    unittest.main()
