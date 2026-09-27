"""Dublês dos testes de apps/i_agora (portados de Frontend/agent_backend/tests, 2026-09-27). Sem rede:
a fonte do extrato é um dublê explícito e o CSV da verdade é um ficheiro temporário com 5 pessoas."""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import conversas_apoio  # noqa: F401  (configura o Django)

from django.test import Client

from apps.context_agent_datadriven.services import perfil_usuario as pu
from apps.conversas import views as conversas_views
from apps.conversas.service import ConversationService
from apps.i_agora import sessao, views
from apps.i_agora.fonte import SourceUnavailable
from apps.i_agora.models import ConfirmacaoPlano, PlanoAtivo, PlanoIAgora

REFS = ['00108ccd-699c-453a-a9f9-a66aad6e03e5', '001221d1-3626-45c1-807a-990502adf808',
        '00ac49e5-4660-4214-b994-2122c59e1b92', '00cab281-99de-4b37-9c08-62bf796640b1',
        '0a1b2c3d-0000-4000-8000-000000000005']
NOMES = ['Maria', 'Eduardo', 'Ana', 'Bruno', 'Carla']
CSV = 'indice,id_usuario,nome,genero,movimentos,meses,primeiro_anomes,ultimo_anomes\n' + ''.join(
    f'{i + 1},{r},{n},{"F" if i % 2 == 0 else "M"},400,12,202501,202512\n' for i, (r, n) in enumerate(zip(REFS, NOMES)))
ROOT = '/api/v1/context-agent/i-agora/'
BOOT = '/api/v1/context-agent/conversas/sessao/'
MSG = '/api/v1/context-agent/conversas/mensagens/'
ORIGEM = 'http://localhost:3000'
SEAL = {'source': 'TEST_FIXTURE', 'nature': 'sintetica', 'measuredAt': '2026-09-27T00:00:00Z', 'cache': False}


def snapshot(ref=REFS[0], index=1):
    return {'client_ref': ref, 'index': index, 'reference_month': '2025-11', 'inflows': '3000.00', 'outflows': '3200.00',
            'categories': {'Delivery': '600.00', 'Lojas e sites': '450.00'}, 'seal': dict(SEAL)}


class Seq:
    """Sorteio injetado: devolve as posições dadas, em ordem (mod n); conta os sorteios."""
    def __init__(self, *values):
        self.values = list(values)
        self.calls = 0

    def randrange(self, n):
        v = self.values[self.calls % len(self.values)]
        self.calls += 1
        return v % n


class Source:
    """Mesmo contrato de FonteExtrato: customers() e load_ref(ref)."""
    def __init__(self, refs=REFS):
        self.refs = list(refs)
        self.loaded = []
        self.fail = 0

    def customers(self):
        return list(self.refs)

    def load_ref(self, ref):
        if self.fail:
            self.fail -= 1
            raise SourceUnavailable('BigQuery indisponível (simulado).')
        if ref not in self.refs:
            raise SourceUnavailable('Cliente sorteado não está no catálogo.')
        self.loaded.append(ref)
        return snapshot(ref, self.refs.index(ref) + 1)


def _sessoes_ids():
    from apps.context_agent_datadriven.models import SessaoPerfilUsuario
    return set(SessaoPerfilUsuario.objects.values_list('sessao_id', flat=True))


def limpar_novos(antes):
    """Apaga só as sessões criadas pelo teste e os planos delas (nunca o que já estava no banco)."""
    from apps.context_agent_datadriven.models import SessaoPerfilUsuario
    novos = _sessoes_ids() - antes
    donos = ['sessao:' + s for s in novos] + ['a', 'b', 'owner-a', 'other-owner']
    for model in (PlanoIAgora, PlanoAtivo, ConfirmacaoPlano):
        model.objects.filter(dono__in=donos).delete()
    SessaoPerfilUsuario.objects.filter(sessao_id__in=novos).delete()


class IAgoraBase(unittest.TestCase):
    """CSV temporário, fonte falsa, sorteio determinístico e conversa demo (sem Gemini)."""
    rng = (2, 4, 1, 3, 0)

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        csv = Path(self.pasta.name) / 'usuarios_verdade.csv'
        csv.write_text(CSV, encoding='utf-8')
        self.src = Source()
        self.rng_obj = Seq(*self.rng)
        self.service = ConversationService()
        for p in (patch.object(pu, 'ARQUIVO_CSV', csv), patch.object(views, 'source', lambda: self.src),
                  patch.object(sessao, 'RNG', self.rng_obj),
                  patch.object(conversas_views, 'get_service', lambda: self.service)):
            p.start()
            self.addCleanup(p.stop)
        pu._base['mtime'] = None
        # Os ganchos da conversa correm o ORM numa thread (persistencia._fora_do_laco), com conexão nova ao banco
        # configurado. teardown_databases (test_d4_* e test_fechamento_* criam banco de teste em memória) devolve o
        # NAME, mas o backend SQLite não fecha conexão em memória: a thread principal continuaria no banco em memória
        # e a thread da conversa no ficheiro. Fecha à força a conexão principal para as duas lerem o mesmo banco.
        from django.db import connection
        from django.db.backends.base.base import BaseDatabaseWrapper
        if connection.connection is not None and not connection.in_atomic_block:
            BaseDatabaseWrapper.close(connection)
        self.antes = _sessoes_ids()
        limpar_novos(self.antes)

    def tearDown(self):
        limpar_novos(self.antes)
        pu._base['mtime'] = None
        self.pasta.cleanup()

    # ---------------------------------------------------------------- cliente HTTP como o front

    def session(self, csrf=False):
        c = Client(enforce_csrf_checks=csrf)
        r = c.get(BOOT)
        self.assertEqual(r.status_code, 200, r.content)
        return c

    def h(self, c):
        return {'HTTP_X_CSRFTOKEN': c.cookies['csrftoken'].value, 'HTTP_ORIGIN': ORIGEM}

    def send(self, c, method, path, data=None, **extra):
        body = json.dumps(data) if data is not None else ''
        return getattr(c, method)(ROOT + path, body, content_type='application/json', **{**self.h(c), **extra})

    def profile(self, c):
        r = c.get(ROOT + 'perfil/')
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()['state']['profile']['person'], r.json()

    def open_(self, c, **extra):
        r = self.send(c, 'post', 'sessao/abertura/', {'origem': 'fab', **extra})
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()['person']

    def owner(self, c):
        return 'sessao:' + conversas_views.sessao_de(_Req(c))[0]


class _Req:
    """Só o que sessao_de lê de um request: META e COOKIES do client."""
    def __init__(self, c):
        self.META = {}
        self.GET = {}
        self.COOKIES = {k: v.value for k, v in c.cookies.items()}


def copia(x):
    return deepcopy(x)
