# Arquivado em 2026-09-27 (Decisão D-3): trecho de tests/test_quatro_rotas.py que testava o comportamento
# antigo de POST /api/v1/context-agent/enviar-mensagem/ (antes do 410 Gone). Não roda sozinho: depende de
# CsvTemporario, RespostaGoogle, COM_CHAVE, SEM_CHAVE, NOME_DEMO_928 e pu definidos no módulo original.
# A versão viva (que afirma o 410) está em tests/test_quatro_rotas.py, classe EnviarMensagemTest.

# =================================================================== 2. enviar-mensagem
URL_ENVIAR = '/api/v1/context-agent/enviar-mensagem/'


class EnviarMensagemTest(CsvTemporario):
    """Contrato ATUAL: identidade = cliente demo (cliente_id / cliente_nome do corpo, sessão no SQLite). Ignora X-Sessao-Id."""

    def setUp(self):
        super().setUp()
        from django.db import transaction
        self._atomic = transaction.atomic()
        self._atomic.__enter__()

        def desfazer():
            transaction.set_rollback(True)
            self._atomic.__exit__(None, None, None)
        self.addCleanup(desfazer)
        self.real = pu.definir_usuario('928')['sessao_id']

    def post(self, corpo, **extra):
        return Client().post(URL_ENVIAR, data=json.dumps(corpo), content_type='application/json', **extra)

    @staticmethod
    def instrucao(abrir):
        return json.loads(abrir.call_args_list[0].args[0].data)['system_instruction']['parts'][0]['text']

    def test_sem_identidade_no_corpo_usa_cliente_demo_42(self):
        """Documenta: sem cliente_id o prompt atende 'Cliente Itaú (#42)' e a sessão SQLite é do cliente_id 42."""
        with mock.patch.dict(os.environ, COM_CHAVE), \
                mock.patch('urllib.request.urlopen', return_value=RespostaGoogle('Olá!')) as abrir:
            r = self.post({'mensagem': 'oi'})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn('Atendendo Cliente Itaú (#42)', self.instrucao(abrir))
        self.assertEqual(r.json()['cliente_id'], 42)
        self.assertEqual(list(ConversaAgenteSessao.objects.values_list('cliente_id', 'cliente_nome')), [(42, 'Cliente Itaú')])

    def test_x_sessao_id_do_usuario_real_e_ignorado(self):
        """Documenta: com X-Sessao-Id do real 928 (Joana), o nome real nunca chega ao prompt; vale o cliente_id demo."""
        with mock.patch.dict(os.environ, COM_CHAVE), \
                mock.patch('urllib.request.urlopen', return_value=RespostaGoogle('Olá!')) as abrir:
            r = self.post({'mensagem': 'quem sou eu?', 'cliente_id': 928, 'cliente_nome': NOME_DEMO_928},
                          HTTP_X_SESSAO_ID=self.real)
        self.assertEqual(r.status_code, 200)
        instrucao = self.instrucao(abrir)
        self.assertNotIn('Joana', instrucao)
        self.assertNotIn(REAL_928, instrucao)
        self.assertIn(f'{NOME_DEMO_928} (#928)', instrucao)
        self.assertIn('score comportamental (750)', instrucao)  # score padrão do demo, não medido

    def test_sem_modelo_503_contingencia_rotulada_e_nada_gravado(self):
        """Sem chave: 503, origem 'contingencia', sucesso False, provedor/modelo null, texto rotulado e nada gravado."""
        with mock.patch.dict(os.environ, SEM_CHAVE), mock.patch('urllib.request.urlopen') as abrir:
            r = self.post({'mensagem': 'quero investir', 'cliente_id': 7})
        abrir.assert_not_called()
        self.assertEqual(r.status_code, 503)
        c = r.json()
        self.assertEqual((c['sucesso'], c['origem_resposta']), (False, 'contingencia'))
        self.assertIsNone(c['protocolo_negociacao']['modelo_utilizado'])
        self.assertIn('API_KEY_SECRECT', c['erro'])
        self.assertTrue(c['resposta_agente'])
        self.assertEqual(MensagemAgenteRegistro.objects.count(), 0)

    def test_prova_negativa_modelo_que_vaza_score_nao_sai(self):
        """Prova negativa: resposta do modelo com 'score: 187' é reprovada (503) e o texto não aparece no HTTP."""
        with mock.patch.dict(os.environ, COM_CHAVE), \
                mock.patch('urllib.request.urlopen', return_value=RespostaGoogle('Seu score: 187')):
            r = self.post({'mensagem': 'qual meu score?', 'cliente_id': 3})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()['eval_harness']['eval_status'], 'REPROVADO_VAZAMENTO')
        self.assertNotIn('score: 187', r.content.decode('utf-8'))

    def test_prova_negativa_corpo_invalido_400(self):
        """Prova negativa: mensagem ausente/vazia e cliente_id booleano dão 400 {erro}."""
        with mock.patch.dict(os.environ, SEM_CHAVE):
            for corpo in ({}, {'mensagem': '  '}, {'mensagem': 'oi', 'cliente_id': True}):
                with self.subTest(corpo=corpo):
                    r = self.post(corpo)
                    self.assertEqual(r.status_code, 400)
                    self.assertEqual(set(r.json()), {'erro', 'tempo_resposta_ms'})

    @unittest.expectedFailure
    def test_i1_usuario_real_nao_recebe_dados_do_cliente_demo(self):
        """I1 — vira verde quando a rota for corrigida/arquivada: com sessão do real 928, nada do demo (ou 410)."""
        # Reproduz o bug do docs/backlog.md (I1): o front manda cliente_id=928 e o nome do demo; sem modelo, a
        # contingência cumprimenta "Olá, Eduarda Soares!" a pessoa real 928 (Joana no CSV de teste).
        with mock.patch.dict(os.environ, SEM_CHAVE), mock.patch('urllib.request.urlopen'):
            r = self.post({'mensagem': 'oi', 'cliente_id': 928, 'cliente_nome': NOME_DEMO_928},
                          HTTP_X_SESSAO_ID=self.real)
        if r.status_code == 410:
            return
        corpo = r.content.decode('utf-8')
        self.assertNotIn('Eduarda', corpo)
        self.assertFalse(ConversaAgenteSessao.objects.filter(cliente_id=928).exists(),
                         'a pessoa real 928 foi gravada como sessão do cliente demo 928 no SQLite')
