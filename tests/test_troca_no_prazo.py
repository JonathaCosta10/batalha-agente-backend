"""503 real do dono, 2026-09-27 13:35:26 BRT (:3000 -> :8000 em 9152041): input_guard 3.1-flash-lite ok 6375 ms,
generate 3.1-flash-lite ok 9297 ms, output_guard 3.1-flash-lite TimeoutError 10078 ms (teto fixo de 10 s), output_guard
3.6-flash 503 em 1156 ms -> fim do turno com 503 e ~18 s ainda livres em PRAZO_TURNO (45 s). Resfriamentos na hora:
3.5-flash-lite cota_dia, 3.1-flash-lite timeout, 3.6-flash indisponível.

Causa: (1) teto fixo de 10 s no output_guard, curto para 3.1-flash-lite com 7-9 mil tokens de entrada; (2) erros_api
1.3.0 admitia UMA nova chamada HTTP por etapa, então o 503 do 2º modelo encerrava a etapa com prazo sobrando.
Correção (erros_api 1.4.0): timeout adaptativo por tentativa e troca pela ordem da etapa enquanto couber no prazo.
Nada chama rede: o transporte é um dublê com roteiro.
"""
import unittest

import conversas_apoio  # noqa: F401  (django.setup)
from conversas_apoio import payload, run

from apps.conversas import gateway as gw_mod
from apps.conversas import roteador as rt
from apps.conversas.gateway import ErroProvedor, GeminiGateway
from apps.conversas.service import ConversationService

LITE31, LITE35, FLASH36, FLASH35 = ('gemini-3.1-flash-lite', 'gemini-3.5-flash-lite', 'gemini-3.6-flash',
                                    'gemini-3.5-flash')
DRAFT = ('{"reply":"Um fluxo negativo não comprova atraso. Há algum pagamento vencido?","status":"needs_clarification",'
         '"capabilities":["orcamento"],"claims":[],"missing_data":[],"projection_proposal":null,'
         '"commitment_proposal":null}')


def resposta(texto, modelo):
    return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': texto}]}}], 'modelVersion': modelo}


def guard(decisao, modelo):
    return resposta('{"decision":"%s","reason_codes":[],"constraints":[],"policy_version":"1.0"}' % decisao, modelo)


class Relogio:
    t = 1000.0

    def __call__(self):
        return self.t


def servico(roteiro, prazo_s=45):
    """roteiro: lista de (modelo esperado, resposta | exceção), na ordem das chamadas ao provedor."""
    chamadas, timeouts = [], []
    fila = list(roteiro)

    def transporte(modelo, corpo, timeout=None):
        chamadas.append(modelo)
        timeouts.append(timeout)
        esperado, r = fila.pop(0)
        assert modelo == esperado, (modelo, esperado, chamadas)
        if isinstance(r, Exception):
            raise r
        return r
    roteador = rt.Roteador(relogio=Relogio())
    # Estado da :8000 às 13:35: 3.5-flash-lite sem cota do dia (resfriado, pulado sem chamada).
    roteador.falhou(LITE35, 429, 'dia', None)
    g = GeminiGateway(transporte=transporte, roteador=roteador)
    s = ConversationService(gateway=g)
    s.timeout = prazo_s
    return s, g, chamadas, timeouts, fila


class CasoDoDono1335(unittest.TestCase):
    def test_timeout_no_1o_503_no_2o_o_3o_responde_200(self):
        s, g, chamadas, timeouts, fila = servico([
            (LITE31, guard('allow', LITE31)),              # input_guard
            (LITE31, resposta(DRAFT, LITE31)),             # generate (3.5-flash-lite resfriado)
            (FLASH36, TimeoutError('timed out')),          # output_guard 1º (cotas 1.2.0: o mais rápido): timeout
            (LITE31, ErroProvedor(503)),                   # output_guard 2º: 503
            (FLASH35, guard('release', FLASH35)),          # output_guard 3º: responde
        ])
        corpo, status = run(s.send('a', payload('São gastos que costumam se repetir, quase toda semana.')))
        self.assertEqual(status, 200, corpo)
        self.assertEqual(fila, [])
        saida = [m['model'] for m in g.metrics if m['stage'] == 'output_guard']
        self.assertEqual(saida, [FLASH36, LITE31, FLASH35])
        self.assertEqual(len(set(saida)), len(saida))       # nunca o mesmo modelo duas vezes na etapa
        self.assertNotIn(LITE35, chamadas)                   # resfriado: pulado sem chamada
        # Timeout adaptativo: o output_guard (última etapa) ganhou mais que o antigo teto fixo de 10 s.
        # Teto por modelo (cotas 1.2.0): 3 x mediana medida com piso de 6 s, nunca acima do timeout_s da etapa.
        self.assertAlmostEqual(timeouts[2], g.roteador.teto_tentativa(FLASH36, 'output_guard'), delta=0.01)
        self.assertLessEqual(timeouts[2], gw_mod.TETO_ADAPTATIVO_S['output_guard'])
        self.assertLessEqual(timeouts[0], gw_mod.TETO_ADAPTATIVO_S['input_guard'])


class ProvaNegativa(unittest.TestCase):
    def _prazo_curto(self, erro):
        # prazo de 4 s: depois do 1º erro do output_guard sobram < MIN_TENTATIVA_S + reserva -> não há 2ª tentativa
        return servico([(LITE31, guard('allow', LITE31)), (LITE31, resposta(DRAFT, LITE31)), (FLASH36, erro)],
                       prazo_s=4)

    def test_prazo_esgotado_timeout_sai_504_timeout_provedor(self):
        s, g, chamadas, _, fila = self._prazo_curto(TimeoutError('timed out'))
        corpo, status = run(s.send('a', payload()))
        self.assertEqual((status, corpo['erro_api']['tipo'], corpo['erro_api']['codigo']), (504, 'timeout_provedor', 504))
        self.assertEqual((fila, len(chamadas)), ([], 3))

    def test_prazo_esgotado_503_sai_503_provedor_indisponivel(self):
        s, g, chamadas, _, fila = self._prazo_curto(ErroProvedor(503))
        corpo, status = run(s.send('a', payload()))
        self.assertEqual((status, corpo['erro_api']['tipo']), (503, 'provedor_indisponivel'))
        self.assertEqual(len(chamadas), 3)

    def test_400_nao_troca_mesmo_com_prazo(self):
        s, g, chamadas, _, _ = servico([(LITE31, guard('allow', LITE31)), (LITE31, resposta(DRAFT, LITE31)),
                                        (FLASH36, ErroProvedor(400))])
        corpo, status = run(s.send('a', payload()))
        self.assertNotEqual(status, 200)
        self.assertEqual(len(chamadas), 3)

    def test_todos_falham_cada_modelo_uma_vez(self):
        s, g, chamadas, _, fila = servico([(LITE31, guard('allow', LITE31)), (LITE31, resposta(DRAFT, LITE31)),
                                           (FLASH36, TimeoutError()), (LITE31, ErroProvedor(503)),
                                           (FLASH35, ErroProvedor(503))])
        corpo, status = run(s.send('a', payload()))
        self.assertEqual(status, 503)
        self.assertEqual(fila, [])                            # 3 tentativas no guard e nenhuma a mais
        saida = [m['model'] for m in g.metrics if m['stage'] == 'output_guard']
        self.assertEqual(sorted(saida), sorted({LITE31, FLASH36, FLASH35}))

    def test_timeout_adaptativo_calculo(self):
        token = gw_mod.PRAZO_TURNO.set(1000.0 + 45)
        try:
            self.assertEqual(gw_mod.timeout_da_tentativa('input_guard', 1000.0), 10)
            self.assertEqual(gw_mod.timeout_da_tentativa('output_guard', 1000.0 + 15.7), 20)
            self.assertAlmostEqual(gw_mod.timeout_da_tentativa('output_guard', 1000.0 + 36), 7)
            self.assertLess(gw_mod.timeout_da_tentativa('output_guard', 1000.0 + 41), gw_mod.MIN_TENTATIVA_S)
        finally:
            gw_mod.PRAZO_TURNO.reset(token)
        self.assertEqual(gw_mod.timeout_da_tentativa('output_guard'), gw_mod.TIMEOUT_POR_ETAPA['output_guard'])


if __name__ == '__main__':
    unittest.main()
