"""Pessoa sorteada por sessão, a MESMA em conversas/* e i-agora/*, até o front pedir outra (next:true).

Portado de Frontend/agent_backend/tests/test_session_pick.py (2026-09-27). Diferença: o sorteio acontece no
GET conversas/sessao/ sem sessão (cria uma sessão de perfil_usuario) e não no i-agora/perfil/; o titular da
sessão é o cliente do plano. Requisito do dono (2026-09-27): sorteio entre os ~1000 da base, mantido em
todas as rotas; next:true sorteia outro, sempre diferente do atual, e passa a valer para tudo.
"""
import json
import unittest

from i_agora_apoio import BOOT, MSG, NOMES, ORIGEM, REFS, ROOT, IAgoraBase

from django.test import Client

from apps.context_agent_datadriven.services import perfil_usuario as pu
from apps.i_agora import sessao

PERSON_KEYS = {'id', 'idUsuario', 'nomeSelo', 'nome', 'primeiroNome', 'genero', 'plan', 'referenceLabel',
               'planPeriodLabel', 'sourceAvailable', 'sourceLabel'}
PROFILE_KEYS = {'person', 'referencePeriod', 'planPeriod', 'situation', 'arrears', 'debt', 'recurringIncome', 'state'}


class SessaoSorteadaTest(IAgoraBase):
    def titular(self, c):
        return c.get(BOOT).json()['usuario']['codigo']

    def test_bootstrap_without_session_draws_and_sets_cookie(self):
        c = Client()
        r = c.get(BOOT)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn('conversa_sessao', c.cookies)
        self.assertIn('csrftoken', c.cookies)
        self.assertEqual(r.json()['usuario']['codigo'], REFS[2])  # Seq sorteia a posição 2
        self.assertEqual(self.rng_obj.calls, 1)

    def test_explicit_unknown_session_is_still_404_and_definir_flow_still_works(self):
        self.assertEqual(Client().get(BOOT + '?sessao_id=nao-existe').status_code, 404)
        sid = pu.definir_usuario(REFS[4])['sessao_id']
        c = Client()
        self.assertEqual(c.get(BOOT + '?sessao_id=' + sid).json()['usuario']['codigo'], REFS[4])
        self.assertEqual(self.profile(c)[0]['idUsuario'], REFS[4])  # i-agora vê o titular definido
        self.assertEqual(self.rng_obj.calls, 0)

    def test_front_real_definir_then_header_x_sessao_id_on_all_routes(self):
        """Front real (batalha-agente-frontend): POST definir/ {usuario: UUID} -> GET sessao/?sessao_id= -> i-agora e
        mensagens com X-Sessao-Id. Nada é sorteado; next:true troca o titular da MESMA sessão."""
        c = Client(enforce_csrf_checks=True)
        r = c.post('/api/v1/context-agent/perfil-usuario/definir/', {'usuario': REFS[3]}, content_type='application/json')
        self.assertEqual(r.status_code, 201, r.content)
        sid = r.json()['sessao_id']
        self.assertEqual(c.get(BOOT + '?sessao_id=' + sid).json()['usuario']['codigo'], REFS[3])
        hs = {'HTTP_X_SESSAO_ID': sid, 'HTTP_X_CSRFTOKEN': c.cookies['csrftoken'].value, 'HTTP_ORIGIN': ORIGEM}
        sem_cookie = Client(enforce_csrf_checks=True)  # só o header identifica a sessão
        sem_cookie.cookies['csrftoken'] = c.cookies['csrftoken'].value
        r = sem_cookie.get(ROOT + 'perfil/', HTTP_X_SESSAO_ID=sid)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['person']['idUsuario'], REFS[3])
        r = sem_cookie.post(MSG, json.dumps({'schema_version': '1.0', 'conversation_id': None, 'client_message_id': 'm1',
                                             'message': 'Oi'}), content_type='application/json', **hs)
        self.assertEqual(r.status_code, 200, r.content)
        r = sem_cookie.post(ROOT + 'sessao/abertura/', json.dumps({'origem': 'fab', 'next': True}),
                            content_type='application/json', **hs)
        self.assertEqual(r.status_code, 201, r.content)
        novo = r.json()['person']['idUsuario']
        self.assertNotEqual(novo, REFS[3])
        self.assertEqual(c.get(BOOT + '?sessao_id=' + sid).json()['usuario']['codigo'], novo)
        self.assertEqual(self.rng_obj.calls, 1)

    def test_same_titular_in_conversas_and_i_agora_until_next(self):
        c = self.session(csrf=True)
        codigo = self.titular(c)
        first, _ = self.profile(c)
        again, _ = self.profile(c)
        opened = self.open_(c)
        self.assertEqual({first['idUsuario'], again['idUsuario'], opened['idUsuario'], codigo}, {REFS[2]})
        self.assertEqual(self.rng_obj.calls, 1)
        self.assertEqual(self.src.loaded, [REFS[2]])  # a fonte é lida uma vez
        # A conversa fala com o mesmo titular (principal e titular da sessão).
        r = c.post(MSG, json.dumps({'schema_version': '1.0', 'conversation_id': None, 'client_message_id': 'm1',
                                    'message': 'Oi'}), content_type='application/json',
                   HTTP_X_CSRFTOKEN=c.cookies['csrftoken'].value, HTTP_ORIGIN=ORIGEM)
        self.assertEqual(r.status_code, 200, r.content)
        # next:true troca para outro, diferente do atual, e vale para TODAS as rotas.
        after = self.open_(c, next=True)
        self.assertNotEqual(after['idUsuario'], REFS[2])
        self.assertEqual(self.titular(c), after['idUsuario'])
        self.assertEqual(self.profile(c)[0]['idUsuario'], after['idUsuario'])
        self.assertEqual(c.get(ROOT + 'plano/').json()['state']['profile']['person']['idUsuario'], after['idUsuario'])
        self.assertEqual(self.open_(c)['idUsuario'], after['idUsuario'])
        # "Reiniciar" limpa o plano e mantém o cliente.
        self.assertEqual(self.send(c, 'delete', 'plano/').status_code, 200)
        self.assertEqual(self.profile(c)[0]['idUsuario'], after['idUsuario'])

    def test_next_never_repeats_current(self):
        c = self.session(csrf=True)
        atual = self.titular(c)
        for _ in range(8):
            novo = self.open_(c, next=True)['idUsuario']
            self.assertNotEqual(novo, atual)
            atual = novo

    def test_retry_after_failed_load_returns_same_drawn_client(self):
        self.src.fail = 1
        c = self.session()
        self.assertEqual(c.get(ROOT + 'perfil/').status_code, 503)
        person, _ = self.profile(c)  # "Tentar de novo" do front
        self.assertEqual(person['idUsuario'], REFS[2])
        self.assertEqual(self.rng_obj.calls, 1)

    def test_two_sessions_get_different_clients(self):
        self.assertEqual([self.titular(self.session()) for _ in range(2)], [REFS[2], REFS[4]])

    def test_negative_proof_fixed_index_is_rejected(self):
        self.assertGreater(len({self.titular(self.session()) for _ in range(5)}), 1)
        antigo = sessao.sortear
        try:
            sessao.sortear = lambda users=None, exclude=None: sessao.catalogo()[0]  # regra antiga: sempre a posição 1
            fixed = [self.titular(self.session()) for _ in range(5)]
        finally:
            sessao.sortear = antigo
        self.assertEqual(fixed, [REFS[0]] * 5)
        with self.assertRaises(AssertionError):
            self.assertGreater(len(set(fixed)), 1)

    def test_profile_shape_and_identity_not_invented(self):
        person, payload = self.profile(self.session())
        self.assertEqual(set(payload), PROFILE_KEYS)
        self.assertEqual(set(person), PERSON_KEYS)
        self.assertEqual(person['nome'], NOMES[2])
        self.assertEqual(person['primeiroNome'], NOMES[2])
        self.assertIsNone(person['genero'])
        self.assertEqual(person['nomeSelo']['natureza'], 'nome_gerado')
        texto = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn('da base', texto)
        self.assertNotIn('NAO_INFORMADO', texto)


class SorteioTest(unittest.TestCase):
    def test_draw_bounds_with_system_random(self):
        seen = {sessao.sortear(REFS) for _ in range(400)}
        self.assertTrue(seen <= set(REFS) and len(seen) > 1)
        self.assertTrue(all(sessao.sortear(REFS, exclude=REFS[1]) != REFS[1] for _ in range(200)))
        self.assertEqual(sessao.sortear(['only'], exclude='only'), 'only')

    def test_real_catalog_is_the_csv_of_about_1000(self):
        self.assertEqual(len(sessao.catalogo()), 1000)


if __name__ == '__main__':
    unittest.main()
