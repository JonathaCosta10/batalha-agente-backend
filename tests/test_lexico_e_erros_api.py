"""Catálogo lexical contextualizado e tratamento conhecido de erros de API (400/404/429/503/504)."""
import asyncio
import socket
import unittest
import urllib.error

import conversas_apoio  # noqa: F401  (django.setup)
from conversas_apoio import FakeGateway, payload, run

from desafio_itau.politica import erros_api, lexico
from apps.conversas import interacao_avaliacao as av
from apps.conversas.gateway import ErroProvedor, GeminiGateway, modelo_alternativo
from apps.conversas.rules import safe_text
from apps.conversas.service import ConversationService
from desafio_itau.modelos_llm import MODELO_PRIMEIRA_CHAMADA


def bloqueado(texto):
    return bool(lexico.bloqueios(texto))


class ExemplosDoCatalogo(unittest.TestCase):
    def test_exemplos_declarados_no_json(self):
        for entrada in lexico.carregar().entradas:
            for t in entrada.exemplos_bloqueados:
                with self.subTest(bloqueia=t):
                    self.assertIn(entrada.id, [a['id'] for a in lexico.bloqueios(t)])
            for t in entrada.exemplos_permitidos:
                with self.subTest(permite=t):
                    self.assertFalse(bloqueado(t))


class Contexto(unittest.TestCase):
    def test_negacao_legitima_passa(self):
        for t in ('Nenhum rendimento é garantido.', 'Não existe investimento sem risco.',
                  'Isso não garante aprovação e não é um crédito pré-aprovado.', 'Ninguém tem lucro certo.',
                  'Você não é irresponsável por ter um mês difícil.'):
            with self.subTest(t=t):
                self.assertFalse(bloqueado(t), lexico.avaliar(t))

    def test_prova_negativa_promessa_afirmativa(self):
        for t in ('O rendimento é garantido.', 'Não se preocupe, o rendimento é garantido.',
                  'Não é que não seja garantido.', 'Sem risco nenhum: é lucro certo.',
                  'Seu empréstimo já está aprovado.', 'Você é muito irresponsável.', 'Última chance, aproveite já.'):
            with self.subTest(t=t):
                self.assertTrue(bloqueado(t))

    def test_citacao_educativa(self):
        self.assertFalse(bloqueado('Desconfie de anúncios que prometem “rendimento garantido”.'))
        # aspas sem marcador de citação não bastam
        self.assertTrue(bloqueado('O retorno é “garantido”.'))
        # julgamento não aceita citação
        self.assertTrue(bloqueado('Tem gente que diz: “a culpa é sua”.'))

    def test_variantes_unicode_caixa_acento(self):
        for t in ('GARANTÍDO', 'garan­tido', 'ga​rantido', 'ｇａｒａｎｔｉｄｏ', 'Pré‑aprovado'.replace('‑', '-'),
                  'SEM  RISCO'):
            with self.subTest(t=repr(t)):
                self.assertTrue(bloqueado(t))

    def test_termos_descritivos_sustentados_nao_sao_bloqueados(self):
        for t in ('Há dívida em atraso segundo o extrato.', 'O fluxo do mês ficou negativo.',
                  'Juros e multa aparecem na janela medida.'):
            with self.subTest(t=t):
                self.assertEqual(lexico.avaliar(t), [])

    @unittest.expectedFailure
    def test_limite_conhecido_negacao_sem_pontuacao(self):
        # Medido: sem vírgula separando, "não se assuste" conta como negação. Triagem, não semântica.
        self.assertTrue(bloqueado('Não se assuste o lucro é garantido'))


class Integracao(unittest.TestCase):
    def test_safe_text_deixa_de_reprovar_negacao(self):
        self.assertTrue(safe_text('Nesta conversa não existe crédito pré-aprovado nem rendimento garantido.'))
        self.assertFalse(safe_text('Seu crédito pré-aprovado está disponível.'))
        self.assertFalse(safe_text('A rentabilidade garantida é a melhor parte.'))

    def test_guard_politica_da_interacao(self):
        def nomes(t):
            return {c['nome']: c['resultado'] for c in av.guard_politica(t, None)}
        self.assertEqual(nomes('Nenhum resultado é garantido, mas dá para organizar.')['politica.promessa'], 'APROVADO')
        self.assertEqual(nomes('Com esse plano o resultado é garantido.')['politica.promessa'], 'REPROVADO')
        self.assertEqual(nomes('Você é descontrolada com dinheiro.')['politica.julgamento'], 'REPROVADO')
        self.assertEqual(nomes('Só hoje: imperdível!')['politica.pressao'], 'REPROVADO')

    def test_modelo_com_julgamento_nao_e_liberado(self):
        service = ConversationService(gateway=FakeGateway(reply='Você é irresponsável: gastou demais.'))
        body, status = run(service.send('a', payload('Como estou?')))
        self.assertEqual((status, body['contrato']['estado']), (503, 'INDISPONIVEL'))
        self.assertNotIn('irrespons', body['reply'])


class TabelaErros(unittest.TestCase):
    def test_cinco_codigos_conhecidos(self):
        self.assertEqual(sorted(erros_api.carregar().erros),
                         ['400', '401', '403', '404', '405', '409', '429', '503', '504'])
        for codigo in (400, 404, 429, 503, 504):
            bloco = erros_api.erro_api(codigo)
            with self.subTest(codigo=codigo):
                self.assertEqual(bloco['codigo'], codigo)
                self.assertNotIn('{', bloco['mensagem'])
                self.assertFalse(erros_api.tratamento(codigo).repetir_mesmo_pedido)
                self.assertEqual(erros_api.erro_api(codigo, 'provedor')['nome'], bloco['nome'])
        self.assertIsNone(erros_api.erro_api(None))  # sucesso da nossa API: sem bloco
        self.assertIsNone(erros_api.erro_api(200))

    def test_codigos_so_da_api_d6(self):
        for codigo, acao in ((401, 'reiniciar_sessao'), (403, 'nao_repetir'), (405, 'nao_repetir'),
                             (409, 'enviar_como_nova')):
            with self.subTest(codigo=codigo):
                self.assertEqual(erros_api.erro_api(codigo)['acao_cliente'], acao)
                self.assertFalse(erros_api.pode_nova_chamada(codigo))

    def test_provedor_fora_da_tabela_vira_nao_classificado_d7(self):
        # Prova negativa: 401 do provedor é chave inválida, nunca "reinicie a sessão".
        b = erros_api.erro_api(401, 'provedor')
        self.assertEqual((b['nome'], b['codigo'], b['origem'], b['acao_cliente']),
                         ('NAO_CLASSIFICADO', 401, 'provedor', 'aguardar_ou_encaminhar'))
        self.assertEqual(erros_api.erro_api(500, 'provedor')['codigo'], 500)
        self.assertEqual(erros_api.erro_api(None, 'provedor')['codigo'], 503)  # 1.2.0: nunca null
        self.assertEqual(erros_api.erro_api(418)['nome'], 'NAO_CLASSIFICADO')

    def test_acoes_do_cliente(self):
        self.assertEqual(erros_api.erro_api(429)['acao_cliente'], 'aguardar_e_tentar_novamente')
        self.assertEqual(erros_api.erro_api(429)['tentar_novamente_em_s'], 30)
        self.assertTrue(erros_api.erro_api(503)['encaminhar_humano'])
        self.assertTrue(erros_api.erro_api(504)['encaminhar_humano'])
        self.assertEqual(erros_api.erro_api(400)['acao_cliente'], 'reformular')
        self.assertIsNone(erros_api.erro_api(400)['tentar_novamente_em_s'])

    def test_status_de_timeout_e_http(self):
        self.assertEqual(erros_api.status_de(ErroProvedor(429)), 429)
        self.assertEqual(erros_api.status_de(TimeoutError()), 504)
        self.assertEqual(erros_api.status_de(socket.timeout()), 504)
        self.assertEqual(erros_api.status_de(urllib.error.URLError(socket.timeout())), 504)
        self.assertIsNone(erros_api.status_de(ValueError('x')))

    def test_espera_no_servidor_limitada(self):
        self.assertEqual(erros_api.espera_no_servidor(503), 2)   # 10 s declarados, teto de 2 s no servidor
        self.assertEqual(erros_api.espera_no_servidor(429), 0)   # cota: outro modelo, sem esperar


def resposta_ok(modelo):
    return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text':
            '{"decision":"allow","reason_codes":[],"constraints":[],"policy_version":"1.0"}'}]}}],
            'modelVersion': modelo}


class NovaChamadaNoGateway(unittest.TestCase):
    def gateway(self, falhas):
        chamadas, esperas = [], []

        def transporte(modelo, corpo):
            chamadas.append(modelo)
            erro = falhas.get(len(chamadas))
            if erro:
                raise erro
            return resposta_ok(modelo)

        async def dormir(s):
            esperas.append(s)
        return GeminiGateway(transporte=transporte, dormir=dormir), chamadas, esperas

    def test_429_troca_de_modelo_sem_esperar(self):
        gw, chamadas, esperas = self.gateway({1: ErroProvedor(429)})
        self.assertEqual(run(gw.input_guard('oi', []))['decision'], 'allow')
        self.assertEqual(chamadas, [MODELO_PRIMEIRA_CHAMADA, modelo_alternativo(MODELO_PRIMEIRA_CHAMADA)])
        self.assertNotEqual(chamadas[0], chamadas[1])
        self.assertEqual(esperas, [])
        self.assertEqual([m['nova_chamada'] for m in gw.metrics], [False, True])
        self.assertEqual(gw.metrics[0]['tratamento_erro'], 'proximo_modelo')

    def test_503_espera_curta_e_uma_nova_chamada(self):
        gw, chamadas, esperas = self.gateway({1: ErroProvedor(503)})
        run(gw.input_guard('oi', []))
        self.assertEqual((len(chamadas), esperas), (2, [2]))

    def test_no_maximo_uma_nova_chamada(self):
        gw, chamadas, _ = self.gateway({1: ErroProvedor(504), 2: ErroProvedor(503)})
        with self.assertRaises(ErroProvedor):
            run(gw.input_guard('oi', []))
        self.assertEqual(len(chamadas), 2)
        self.assertEqual(gw.calls, 2)  # a nova chamada consome orçamento

    def test_prova_negativa_erro_sem_tratamento_nao_repete(self):
        for erro in (ErroProvedor(401), ErroProvedor(500), ValueError('saida malformada')):
            with self.subTest(erro=repr(erro)):
                gw, chamadas, _ = self.gateway({1: erro})
                with self.assertRaises(type(erro)):
                    run(gw.input_guard('oi', []))
                self.assertEqual(len(chamadas), 1)


class EnvelopeDoServico(unittest.TestCase):
    def test_falha_do_provedor_leva_causa_e_acao(self):
        gateway = FakeGateway()

        async def falha(*a, **k):
            raise ErroProvedor(429)
        gateway.generate = falha
        body, status = run(ConversationService(gateway=gateway).send('a', payload()))
        self.assertEqual(status, 429)  # erros_api 1.2.0: cota do provedor -> HTTP 429
        self.assertEqual((body['erro_api']['codigo'], body['erro_api']['origem']), (429, 'provedor'))
        self.assertEqual(body['erro_api']['acao_cliente'], 'aguardar_e_tentar_novamente')

    def test_timeout_do_servico_vira_504(self):
        gateway = FakeGateway()

        async def lento(*a, **k):
            await asyncio.sleep(1)
        gateway.generate = lento
        body, status = run(ConversationService(gateway=gateway, timeout=0.05).send('a', payload()))
        self.assertEqual((status, body['erro_api']['codigo'], body['erro_api']['encaminhar_humano']), (504, 504, True))

    def test_erros_da_propria_api(self):
        service = ConversationService(gateway=FakeGateway())
        body, status = run(service.send('a', {**payload(), 'extra': 1}))
        self.assertEqual((status, body['erro_api']['codigo'], body['erro_api']['origem']), (400, 400, 'api'))
        body, status = run(service.send('a', payload(cid='nao-existe')))
        self.assertEqual((status, body['erro_api']['acao_cliente']), (404, 'reiniciar_sessao'))
        body, status = run(service.send(None, payload()))
        self.assertEqual((status, body['erro_api']['nome'], body['erro_api']['origem']), (401, 'Unauthorized', 'api'))

    def test_falha_do_provedor_sem_status_nao_sai_como_api_d7(self):
        class Quebra(FakeGateway):
            async def generate(self, *a, **k):
                raise RuntimeError('x')
        body, status = run(ConversationService(gateway=Quebra()).send('a', payload()))
        self.assertEqual((status, body['erro_api']['origem'], body['erro_api']['nome']),
                         (503, 'provedor', 'NAO_CLASSIFICADO'))

    def test_bloqueio_por_usuario_nao_global_d11(self):
        import asyncio
        liberar = asyncio.Event()

        class Lento(FakeGateway):
            async def generate(self, *a, **k):
                await liberar.wait()
                return await super().generate(*a, **k)

        async def cenario():
            service = ConversationService(gateway=Lento())
            primeiro = asyncio.create_task(service.send('a', payload(mid='m1')))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            mesmo = await service.send('a', payload(mid='m2'))    # mesmo usuário em curso: 429
            liberar.set()
            outro = await service.send('b', payload(mid='m3'))    # outro usuário: não herda o 429
            return mesmo[1], outro[1], (await primeiro)[1]
        self.assertEqual(run(cenario()), (429, 200, 200))

    def test_ttl_da_conversa_igual_ao_da_sessao_d3(self):
        from apps.context_agent_datadriven.services.perfil_usuario import SESSAO_SEGUNDOS
        self.assertEqual(ConversationService().ttl, SESSAO_SEGUNDOS)
        self.assertEqual(ConversationService(ttl=5).ttl, 5)


if __name__ == '__main__':
    unittest.main()
