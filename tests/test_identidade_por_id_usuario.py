"""Contexto por id_usuario (verificação ponta a ponta, 2026-09-27 10:14-10:40 BRT). Sem rede.

Regra do dono (10:22): o nome vale quando é o `nome_gerado` do MESMO id_usuario (data/usuarios_verdade.csv); o gênero
NUNCA é servido (nem ao cliente, nem ao prompt); índice posicional não sai. E todo erro de conversas/interacao/ chega
com o envelope erro_api (mensagem pt-BR + acao_cliente). Cada teste tem prova negativa: um caso ruim que TEM de reprovar.
"""
import json
import unittest
from unittest import mock

from conversas_apoio import MARIA  # noqa: F401  (faz django.setup)

from django.test import Client  # noqa: E402

from apps.conversas import interacao, interacao_avaliacao as av, interacao_dados as dd  # noqa: E402
from apps.conversas import views_interacao  # noqa: E402
from apps.conversas.service import identity_draft  # noqa: E402

TITULAR_F = {'codigo': MARIA, 'pessoa': 'Maria', 'genero': 'F', 'indice': 1}
TITULAR_M = {**TITULAR_F, 'genero': 'M'}
CONVITE = ('Agora vamos transformar essa oportunidade em um plano. *Topa o desafio de descobrir o seu caminho para '
           'uma vida financeira mais equilibrada?*')


class TitularSemGenero(unittest.TestCase):

    def test_titular_publico_so_id_e_nome_gerado(self):
        pub = interacao.titular_publico(TITULAR_F)
        self.assertEqual(pub, {'id_usuario': MARIA, 'pessoa': 'Maria', 'nome_origem': 'nome_gerado'})
        # prova negativa: o dict da sessão TEM genero e indice; nenhum dos dois pode passar
        self.assertIn('genero', TITULAR_F)
        self.assertNotIn('genero', pub)
        self.assertNotIn('indice', pub)

    def test_instrucao_nao_depende_do_genero(self):
        dados = interacao._dados_sem_consulta(TITULAR_F)
        f = interacao.instrucao('bot.intro', TITULAR_F, dados)
        m = interacao.instrucao('bot.intro', TITULAR_M, dados)
        self.assertEqual(f, m)  # se o gênero vazasse para o prompt, F e M dariam textos diferentes
        self.assertNotRegex(f, r'feminino|masculino|g[eê]nero [FM]\b')
        self.assertIn('Maria', f)

    def test_identidade_em_mensagens_sem_concordancia(self):
        texto = identity_draft(TITULAR_F).reply
        self.assertIn('Maria', texto)
        self.assertIn(MARIA, texto)
        self.assertNotRegex(av.normalizar_texto(texto), r'identificad[ao]')
        self.assertEqual(texto, identity_draft(TITULAR_M).reply)

    def test_guard_genero_reprova_as_duas_formas(self):
        ctx = {'situacao': 'SOBROU', 'situacao_media': 'SOBROU', 'segmento': None, 'valores': [], 'regra': None}
        rep = lambda t: av.avaliar(t, titular=TITULAR_F, contexto=ctx, etapa={}, outros_nomes=['Maria', 'Eduardo'])['reprovados']  # noqa: E731
        self.assertIn('nome.genero', rep('Maria, você está preparada?'))
        self.assertIn('nome.genero', rep('Maria, você está preparado?'))
        self.assertNotIn('nome.genero', rep('Maria, vamos organizar?'))
        # nome de OUTRO id reprova; o nome gerado do mesmo id passa
        self.assertIn('nome.alheio', rep('Eduardo, vamos organizar?'))
        self.assertNotIn('nome.alheio', rep('Maria, vamos organizar?'))


class ConviteNaoReprovaPorEquilibrada(unittest.TestCase):
    """Medido 10:14 BRT: 3 de 3 ids reais tiveram 503 vazio em bot.convite_50_30_20 no modo demo, porque "mais
    equilibrada" contava como afirmação de EQUILIBRIO."""

    def test_convite_passa_com_sobrou_e_faltou(self):
        for sit in (dd.SOBROU, dd.FALTOU):
            self.assertEqual([c for c in av.guard_situacao(CONVITE, sit, sit) if c['resultado'] == av.REPROVADO], [])

    def test_prova_negativa_afirmar_equilibrio_continua_reprovando(self):
        ruim = 'Em média, suas entradas e saídas ficaram equilibradas.'
        self.assertTrue(any(c['resultado'] == av.REPROVADO for c in av.guard_situacao(ruim, dd.SOBROU, dd.SOBROU)))


class ErrosComEnvelope(unittest.TestCase):

    def setUp(self):
        self.c = Client()

    def _post(self, sid='x' * 10, corpo=None):
        return self.c.post('/api/v1/context-agent/conversas/interacao/', json.dumps(corpo or {'etapa': 'bot.intro'}),
                           content_type='application/json', **({'HTTP_X_SESSAO_ID': sid} if sid else {}))

    def _envelope_ok(self, corpo, status):
        api = corpo.get('erro_api') or {}
        self.assertEqual(api.get('codigo'), status)
        self.assertTrue(api.get('acao_cliente'))
        self.assertTrue(isinstance(api.get('mensagem'), str) and len(api['mensagem']) > 20)
        self.assertTrue(corpo.get('mensagem'))

    def test_401_sem_header(self):
        r = self._post(sid=None)
        self.assertEqual(r.status_code, 401)
        self._envelope_ok(r.json(), 401)
        self.assertEqual(r.json()['erro_api']['acao_cliente'], 'reiniciar_sessao')

    def test_503_sem_texto_aprovado_tem_causa_e_acao(self):
        corpo_antigo = {'schema_version': interacao.SCHEMA_VERSION, 'texto': None, 'erro_api': None,
                        'origem_resposta': 'nenhuma'}
        # prova negativa: o corpo que ia à tela antes (medido 10:14) não tem nada que a tela possa mostrar
        with self.assertRaises(AssertionError):
            self._envelope_ok(corpo_antigo, 503)
        with mock.patch.object(views_interacao.perfil_usuario, 'usuario_da_sessao', return_value=TITULAR_F), \
                mock.patch.object(interacao, 'interagir', side_effect=interacao.SemResposta(dict(corpo_antigo))):
            r = self._post()
        self.assertEqual(r.status_code, 503)
        corpo = r.json()
        self._envelope_ok(corpo, 503)
        self.assertEqual(corpo['erro'], 'sem_texto_aprovado')
        self.assertEqual(corpo['schema_version'], interacao.SCHEMA_VERSION)


if __name__ == '__main__':
    unittest.main()
