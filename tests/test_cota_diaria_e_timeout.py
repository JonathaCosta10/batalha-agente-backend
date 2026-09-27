"""429 de cota DIÁRIA do Gemini e timeout por etapa (apps/conversas/gateway.py, backend-22, 2026-09-27).

Medido às 12:29-12:31 BRT: os três modelos homologados devolveram 429 com quotaId
`GenerateRequestsPerDayPerProjectPerModel-FreeTier` (flash-lite 500/dia, flash 20/dia, flash-latest 20/dia). Com a cota
do dia esgotada, repetir o modelo não adianta; o gateway pula o modelo por PAUSA_COTA_DIARIA_S sem chamar o provedor.
A política (erros_api-v1.json) não muda: nenhum pedido repetido, no máximo uma nova chamada, 503 + erro_api 429 ao front.
Nada chama rede: transporte e relógio são dublês.
"""
import io
import json
import unittest
import urllib.error
from unittest.mock import patch

import conversas_apoio  # noqa: F401  (django.setup)
from conversas_apoio import FakeGateway, payload, run

from apps.conversas import gateway as gw
from apps.conversas.gateway import (ErroProvedor, GeminiGateway, PAUSA_COTA_DIARIA_S, TIMEOUT_POR_ETAPA, cota_do_429,
                                    modelo_alternativo)
from apps.conversas.service import ConversationService
from desafio_itau.modelos_llm import MODELO_PRIMEIRA_CHAMADA

ALT = modelo_alternativo(MODELO_PRIMEIRA_CHAMADA)


def corpo_429(quota_id, mensagem='Quota exceeded'):
    # Forma real do corpo (campos conferidos na sonda de 12:29 BRT; valores sintéticos).
    return json.dumps({'error': {'code': 429, 'message': mensagem, 'status': 'RESOURCE_EXHAUSTED', 'details': [
        {'@type': 'type.googleapis.com/google.rpc.QuotaFailure',
         'violations': [{'quotaId': quota_id, 'quotaDimensions': {'model': 'x'}, 'quotaValue': '500'}]},
        {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '35s'}]}}).encode()


def ok(modelo):
    return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text':
            '{"decision":"allow","reason_codes":[],"constraints":[],"policy_version":"1.0"}'}]}}],
            'modelVersion': modelo}


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class CotaDo429(unittest.TestCase):
    def test_classifica_pelo_quota_id(self):
        self.assertEqual(cota_do_429(corpo_429('GenerateRequestsPerDayPerProjectPerModel-FreeTier')), 'dia')
        self.assertEqual(cota_do_429(corpo_429('GenerateRequestsPerMinutePerProjectPerModel-FreeTier')), 'minuto')

    def test_prova_negativa_so_le_quota_id(self):
        # "PerDay" no texto livre não conta; corpo ilegível ou sem detalhes -> None (429 comum).
        self.assertIsNone(cota_do_429(corpo_429('OutraCota', mensagem='limit PerDay reached')))
        for corpo in (b'<html>', b'{}', b'[]', json.dumps({'error': {'details': 'x'}}).encode()):
            with self.subTest(corpo=corpo):
                self.assertIsNone(cota_do_429(corpo))

    def test_transporte_http_leva_cota_e_timeout_da_etapa(self):
        vistos = {}

        def urlopen(pedido, timeout):
            vistos['timeout'] = timeout
            raise urllib.error.HTTPError(pedido.full_url, 429, 'Too Many', {},
                                         io.BytesIO(corpo_429('GenerateRequestsPerDayPerProjectPerModel-FreeTier')))
        with patch.object(gw, 'obter_api_key', return_value=('CHAVE-FALSA', 'env:teste')), \
                patch.object(gw.urllib.request, 'urlopen', urlopen):
            with self.assertRaises(ErroProvedor) as ctx:
                gw.transporte_http('gemini-3.5-flash-lite', {}, timeout=7)
        self.assertEqual((ctx.exception.code, ctx.exception.cota, vistos['timeout']), (429, 'dia', 7))
        self.assertNotIn('Quota', str(ctx.exception))  # nada do corpo na exceção


class PausaDeCotaDiaria(unittest.TestCase):
    def gateway(self, erros):
        """erros: {modelo: ErroProvedor|None} fixo por modelo."""
        chamadas, relogio = [], Relogio()

        def transporte(modelo, corpo):
            chamadas.append(modelo)
            if erros.get(modelo):
                raise erros[modelo]
            return ok(modelo)
        return GeminiGateway(transporte=transporte, relogio=relogio), chamadas, relogio

    def test_modelo_sem_cota_do_dia_nao_e_chamado_de_novo(self):
        g, chamadas, _ = self.gateway({MODELO_PRIMEIRA_CHAMADA: ErroProvedor(429, 'dia')})
        run(g.input_guard('oi', []))
        self.assertEqual(chamadas, [MODELO_PRIMEIRA_CHAMADA, ALT])
        run(g.input_guard('oi de novo', []))
        self.assertEqual(chamadas, [MODELO_PRIMEIRA_CHAMADA, ALT, ALT])  # o primário foi pulado
        self.assertEqual(g.calls, 3)  # o pulo não consome orçamento
        self.assertEqual([m['outcome'] for m in g.metrics][-2:], ['pulado_cota_diaria', 'complete'])
        self.assertEqual(set(g.cota_diaria_esgotada()), {MODELO_PRIMEIRA_CHAMADA})

    def test_prova_negativa_429_por_minuto_ou_sem_tipo_nao_pausa(self):
        for erro in (ErroProvedor(429, 'minuto'), ErroProvedor(429)):
            with self.subTest(cota=erro.cota):
                g, chamadas, _ = self.gateway({MODELO_PRIMEIRA_CHAMADA: erro})
                run(g.input_guard('oi', []))
                run(g.input_guard('oi', []))
                self.assertEqual(chamadas, [MODELO_PRIMEIRA_CHAMADA, ALT] * 2)
                self.assertEqual(g.cota_diaria_esgotada(), {})

    def test_dois_modelos_sem_cota_falham_sem_chamar_o_provedor(self):
        dia = ErroProvedor(429, 'dia')
        g, chamadas, _ = self.gateway({MODELO_PRIMEIRA_CHAMADA: dia, ALT: dia})
        with self.assertRaises(ErroProvedor):
            run(g.input_guard('oi', []))
        self.assertEqual(len(chamadas), 2)
        with self.assertRaises(ErroProvedor) as ctx:
            run(g.input_guard('oi', []))
        self.assertEqual((len(chamadas), ctx.exception.code, g.calls), (2, 429, 2))

    def test_depois_da_pausa_volta_a_sondar_com_uma_chamada_real(self):
        g, chamadas, relogio = self.gateway({MODELO_PRIMEIRA_CHAMADA: ErroProvedor(429, 'dia')})
        run(g.input_guard('oi', []))
        relogio.t += PAUSA_COTA_DIARIA_S + 1
        self.assertEqual(g.cota_diaria_esgotada(), {})
        run(g.input_guard('oi', []))
        self.assertEqual(chamadas[-2:], [MODELO_PRIMEIRA_CHAMADA, ALT])

    def test_front_recebe_429_com_erro_api_429_mesmo_sem_chamada(self):
        dia = ErroProvedor(429, 'dia')
        fake = FakeGateway()
        g, chamadas, _ = self.gateway({MODELO_PRIMEIRA_CHAMADA: dia, ALT: dia})
        fake.input_guard = g.input_guard
        service = ConversationService(gateway=fake)
        corpo, status = run(service.send('a', payload('oi')))
        corpo2, status2 = run(service.send('a', payload('oi', 'msg-002', corpo['conversation_id'])))
        self.assertEqual(len(chamadas), 2)  # a segunda mensagem não chamou o provedor
        for c, s in ((corpo, status), (corpo2, status2)):
            self.assertEqual((s, c['erro_api']['codigo'], c['erro_api']['acao_cliente'], c['erro_api']['origem']),  # HTTP 429 (1.2.0)
                             (429, 429, 'aguardar_e_tentar_novamente', 'provedor'))


class TimeoutPorEtapa(unittest.TestCase):
    def test_guard_e_generate_recebem_o_timeout_da_etapa(self):
        vistos = []

        def transporte(modelo, corpo, timeout=None):
            vistos.append(timeout)
            return ok(modelo)
        g = GeminiGateway(transporte=transporte)
        run(g.input_guard('oi', []))
        self.assertEqual(vistos, [TIMEOUT_POR_ETAPA['input_guard']])

    def test_soma_do_caminho_feliz_cabe_no_servico_e_no_front(self):
        # guard + generate + guard sem nova chamada < timeout do serviço (45 s) < timeout do front (50 s,
        # Frontend/src/services/backend.ts). Prova negativa: generate mais lento que o serviço reprovaria.
        soma = TIMEOUT_POR_ETAPA['input_guard'] + TIMEOUT_POR_ETAPA['generate'] + TIMEOUT_POR_ETAPA['output_guard']
        self.assertLess(soma, ConversationService().timeout)
        self.assertLess(ConversationService().timeout, 50)
        self.assertGreater(TIMEOUT_POR_ETAPA['generate'], TIMEOUT_POR_ETAPA['input_guard'])
        self.assertFalse(10 + 40 + 10 < ConversationService().timeout)


class StatusMostraCotaETimeouts(unittest.TestCase):
    def test_status_lista_modelo_pausado_sem_texto(self):
        from apps.conversas import views
        g = GeminiGateway(relogio=Relogio())
        g.cota_esgotada[MODELO_PRIMEIRA_CHAMADA] = g.relogio() + 600
        with patch.object(views, 'get_service', return_value=ConversationService(gateway=g)):
            corpo = views.estado_harness()
        self.assertEqual(corpo['cota_diaria_esgotada'], {MODELO_PRIMEIRA_CHAMADA: 600})
        self.assertEqual(corpo['limites']['timeout_por_etapa_s'], TIMEOUT_POR_ETAPA)
        with patch.object(views, 'get_service', return_value=ConversationService()):
            self.assertEqual(views.estado_harness()['cota_diaria_esgotada'], {})  # modo demo: sem gateway


if __name__ == '__main__':
    unittest.main()
