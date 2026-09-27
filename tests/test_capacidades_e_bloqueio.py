"""Pedidos do dono 2026-09-27 14:09 e 14:11 BRT (backend-22) e do par frontend-c7.

14:07 na :8000 (9152041): input_guard 3.6-flash 503 -> 3.5-flash 429 (cota_dia) -> ... -> "nenhum sem_modelo_disponivel"
-> 429 ao front com "tente em 30 s", enquanto 3.1-flash-lite só estava resfriado por um timeout (60 s) de outra etapa.

(a) recusa (429 por minuto, 5xx, timeout, resposta inválida) -> próximo NÃO tentado da etapa;
(b) timeout/5xx resfriam só 15 s (transitório); cota_dia e 404 excluem de fato;
(c) todos bloqueados por motivo transitório -> último recurso: o de menor espera;
(d) teto de RPM do processo desvia antes do 429 e não entra no último recurso;
(e) Retry-After / tentar_novamente_em_s = menor espera real da etapa; cota_dia em todos é dita (motivo_provedor);
frontend-c7 (1): resposta de falha não vai ao Gemini no histórico dos turnos seguintes;
capacidades por modelo (cotas-gemini 1.1.0) lidas pelo router e expostas no status.
Nada chama rede.
"""
import copy
import json
import unittest

import conversas_apoio  # noqa: F401  (django.setup)
from conversas_apoio import FakeGateway, payload, run

from apps.conversas import gateway as gw_mod
from apps.conversas import roteador as rt
from apps.conversas.gateway import ErroProvedor, GeminiGateway
from apps.conversas.service import ConversationService

G = rt.carregar().router.etapas['input_guard']
LITE31, FLASH36, LITE35, FLASH35 = G
CFG = rt.carregar().router.resfriamento_s


class Relogio:
    def __init__(self):
        self.t = 5000.0

    def __call__(self):
        return self.t


def ok_guard(modelo):
    return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text':
            '{"decision":"allow","reason_codes":[],"constraints":[],"policy_version":"1.0"}'}]}}], 'modelVersion': modelo}


def gateway(erros, relogio=None):
    chamadas, relogio = [], relogio or Relogio()

    def transporte(modelo, corpo):
        chamadas.append(modelo)
        if erros.get(modelo):
            raise erros[modelo]
        return ok_guard(modelo)
    return GeminiGateway(transporte=transporte, roteador=rt.Roteador(relogio=relogio)), chamadas, relogio


class ResfriamentoTransitorio(unittest.TestCase):
    def test_b_timeout_e_5xx_resfriam_no_maximo_15_s(self):
        self.assertLessEqual(CFG.timeout, 15)
        self.assertLessEqual(CFG.indisponivel, 15)
        r = rt.Roteador(relogio=Relogio())
        r.falhou(LITE31, 504)
        r.falhou(FLASH36, 503)
        r.relogio.t += 16
        self.assertIsNone(r.bloqueio(LITE31))
        self.assertIsNone(r.bloqueio(FLASH36))

    def test_b_prova_negativa_cota_dia_e_404_continuam_excluidos(self):
        r = rt.Roteador(relogio=Relogio())
        r.falhou(LITE35, 429, 'dia')
        r.falhou(FLASH35, 404)
        r.relogio.t += 16
        self.assertEqual((r.bloqueio(LITE35), r.bloqueio(FLASH35)), (429, 404))
        self.assertNotIn('cota_dia', r.dados.router.transitorios)
        self.assertNotIn('nao_encontrado', r.dados.router.transitorios)


class UltimoRecurso(unittest.TestCase):
    def test_c_caso_14_07_todos_bloqueados_tenta_o_de_menor_espera_transitoria(self):
        g, chamadas, relogio = gateway({})
        r = g.roteador
        r.falhou(LITE35, 429, 'dia')
        r.falhou(FLASH35, 429, 'dia')
        r.falhou(FLASH36, 503)             # 15 s
        relogio.t += 5
        r.falhou(LITE31, 504)              # 15 s, mais recente -> espera maior
        self.assertEqual(r.escolher('input_guard'), FLASH36)   # antes: None -> sem_modelo_disponivel -> 429
        self.assertEqual(run(g.input_guard('oi', []))['decision'], 'allow')
        self.assertEqual(chamadas, [FLASH36])

    def test_c_segue_para_o_outro_transitorio_sem_repetir(self):
        g, chamadas, relogio = gateway({FLASH36: ErroProvedor(503)})
        r = g.roteador
        for m in (LITE35, FLASH35):
            r.falhou(m, 429, 'dia')
        r.falhou(FLASH36, 503)
        relogio.t += 5
        r.falhou(LITE31, 504)
        run(g.input_guard('oi', []))
        self.assertEqual(chamadas, [FLASH36, LITE31])

    def test_c_prova_negativa_todos_sem_cota_do_dia_nenhuma_chamada_429_motivo_cota_dia(self):
        g, chamadas, _ = gateway({})
        for m in G:
            g.roteador.falhou(m, 429, 'dia')
        with self.assertRaises(ErroProvedor) as ctx:
            run(g.input_guard('oi', []))
        self.assertEqual((chamadas, ctx.exception.code, ctx.exception.motivo_bloqueio), ([], 429, 'cota_dia'))
        self.assertGreater(ctx.exception.espera_restante_s, 800)   # ~900 s, não os 30 fixos

    def test_d_teto_de_rpm_desvia_antes_e_nao_e_ultimo_recurso(self):
        g, chamadas, relogio = gateway({})
        r = g.roteador
        for _ in range(r.rpm_teto(LITE31) - r.dados.router.rpm_margem):
            r.chamou(LITE31)
        self.assertEqual(r.escolher('input_guard'), FLASH36)          # desvia sem chamar o saturado
        for m in (FLASH36, LITE35, FLASH35):
            r.falhou(m, 429, 'dia')
        self.assertIsNone(r.escolher('input_guard'))                  # só o saturado: não é último recurso


class EsperaReal(unittest.TestCase):
    def test_e_retry_after_e_a_menor_espera_da_etapa(self):
        class Bloqueado(FakeGateway):
            async def input_guard(self, *a, **k):
                erro = ErroProvedor(429, 'resfriamento')
                erro.espera_restante_s, erro.motivo_bloqueio = 7, 'cota_minuto'
                raise erro
        corpo, status = run(ConversationService(gateway=Bloqueado()).send('a', payload()))
        e = corpo['erro_api']
        self.assertEqual((status, e['tipo'], e['tentar_novamente_em_s'], e['motivo_provedor']),
                         (429, 'cota_provedor', 7, 'cota_minuto'))

    def test_e_prova_negativa_sem_espera_real_fica_o_da_politica(self):
        class Fora(FakeGateway):
            async def input_guard(self, *a, **k):
                raise ErroProvedor(503)
        corpo, _ = run(ConversationService(gateway=Fora()).send('a', payload()))
        self.assertNotIn('motivo_provedor', corpo['erro_api'])
        self.assertEqual(corpo['erro_api']['tentar_novamente_em_s'], 10)   # linha 503 da política

    def test_e_espera_restante_do_router(self):
        r = rt.Roteador(relogio=Relogio())
        r.falhou(LITE31, 429, 'minuto', 7)
        for m in (FLASH36, LITE35, FLASH35):
            r.falhou(m, 429, 'dia')
        self.assertEqual(r.espera_restante('input_guard'), 7)
        self.assertEqual(r.motivo_bloqueio('input_guard'), 'cota_minuto')
        self.assertIsNone(rt.Roteador(relogio=Relogio()).espera_restante('input_guard'))


class HistoricoSemFalha(unittest.TestCase):
    def test_c7_resposta_de_falha_nao_vai_ao_modelo_no_turno_seguinte(self):
        vistos = []

        class UmaFalha(FakeGateway):
            falhou = False

            async def generate(self, message, context, history, constraints, titular=None):
                vistos.append(list(history))
                if not UmaFalha.falhou:
                    UmaFalha.falhou = True
                    raise ErroProvedor(503)
                return await super().generate(message, context, history, constraints, titular)
        s = ConversationService(gateway=UmaFalha())
        r1, st1 = run(s.send('a', payload('primeira', 'm1')))
        self.assertEqual(st1, 503)
        r2, st2 = run(s.send('a', payload('segunda', 'm2', r1['conversation_id'])))
        self.assertEqual(st2, 200)
        self.assertEqual(vistos[1], [])                               # a falha não entrou como fala do modelo
        r3, _ = run(s.send('a', payload('terceira', 'm3', r1['conversation_id'])))
        self.assertEqual([h['text'] for h in vistos[2]], ['segunda', r2['reply']])   # prova negativa: sucesso entra
        self.assertEqual(len(s.sessions[('a', r1['conversation_id'])]), 6)          # conta para max_turns


class Capacidades(unittest.TestCase):
    def test_capacidades_declaradas_para_toda_a_ordem_e_lidas_pelo_router(self):
        dados = rt.carregar()
        self.assertEqual(dados.versao, '1.1.0')
        r = rt.Roteador(relogio=Relogio())
        for etapa, ordem in dados.router.etapas.items():
            for m in ordem:
                cap = dados.capacidades[m]
                self.assertIn(etapa, cap.etapas)
                self.assertEqual(r.timeout_s(m, etapa), cap.timeout_s[etapa])
                for nome, lim in cap.limites.items():
                    self.assertEqual(lim.estado == 'NAO_MEDIDO', lim.valor is None)
                for lat in cap.latencia_mediana_ms.values():
                    self.assertEqual(lat.estado == 'NAO_MEDIDO', lat.valor_ms is None)
        self.assertEqual(r.rpm_teto(FLASH36), dados.capacidades[FLASH36].limites['rpm'].valor)

    def test_prova_negativa_modelo_na_ordem_sem_capacidade_da_etapa_reprova(self):
        bruto = json.loads(rt.ARQUIVO.read_text(encoding='utf-8'))
        ruim = copy.deepcopy(bruto)
        del ruim['capacidades'][LITE31]['etapas']['output_guard']
        with self.assertRaises(ValueError):
            rt.validar(ruim)
        ruim = copy.deepcopy(bruto)
        ruim['capacidades'][LITE31]['latencia_mediana_ms']['generate']['estado'] = 'inventado'
        with self.assertRaises(ValueError):
            rt.validar(ruim)

    def test_teto_do_modelo_limita_a_tentativa(self):
        token = gw_mod.PRAZO_TURNO.set(1000.0 + 45)
        try:
            self.assertEqual(gw_mod.timeout_da_tentativa('output_guard', 1000.0, teto=12), 12)
        finally:
            gw_mod.PRAZO_TURNO.reset(token)

    def test_status_expoe_capacidades_com_estado_vivo(self):
        r = rt.Roteador(relogio=Relogio())
        r.falhou(LITE35, 429, 'dia')
        r.chamou(FLASH36)
        caps = r.estado()['capacidades']
        self.assertEqual(caps[LITE35]['agora']['estado'], 'resfriando')
        self.assertEqual((caps[LITE35]['agora']['motivo'], caps[LITE35]['agora']['transitorio']), ('cota_dia', False))
        self.assertEqual((caps[FLASH36]['agora']['estado'], caps[FLASH36]['agora']['rpm_usado']), ('livre', 1))
        self.assertIn('falhas_observadas', caps[LITE31])


if __name__ == '__main__':
    unittest.main()
