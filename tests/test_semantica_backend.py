"""Correções semânticas de 2026-09-27 (docs/CHANGELOG-semantica.md).

Cada grupo tem a sua prova negativa: um caso ruim que TEM de reprovar.
Corre com o comando de sempre (unittest discover): este módulo liga o Django
e cria um banco de teste em memória pelas MIGRAÇÕES (não toca no db.sqlite3).
"""

import json
import logging
import os
import sqlite3
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")
import django  # noqa: E402

django.setup()

from django.apps import apps as django_apps  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import IntegrityError, connection, transaction  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import setup_databases, setup_test_environment, teardown_databases, teardown_test_environment  # noqa: E402

from apps.context_agent_datadriven.models import ConversaAgenteSessao, MensagemAgenteRegistro  # noqa: E402
from apps.context_agent_datadriven.templates.context_agent_painel_html import HTML_PAINEL  # noqa: E402
from apps.recomendacao.models import FeatureFlagInteracaoTelaIAI  # noqa: E402

SEM_CHAVE = {
    "API_KEY_SECRECT": "",
    "GEMINI_API_KEY": "",
    "GSCONSOLE_SECRET": "",
    "GOOGLE_API_KEY": "",
    "SECRETS_FILE": str(Path(tempfile.gettempdir()) / "nao-existe" / ".secrets"),
}
CHAVE_TESTE = "AIzaSyTESTE-chave-falsa-0123456789abcd"
COM_CHAVE = {**SEM_CHAVE, "API_KEY_SECRECT": CHAVE_TESTE}

_estado_bd = None


def setUpModule():
    global _estado_bd
    # 4xx são o esperado em vários testes; 5xx continuam a aparecer (ERROR).
    logging.getLogger("django.request").setLevel(logging.ERROR)
    setup_test_environment()
    _estado_bd = setup_databases(verbosity=0, interactive=False)


def tearDownModule():
    teardown_databases(_estado_bd, verbosity=0)
    teardown_test_environment()


class RespostaGoogle:
    """Resposta falsa de urlopen (generateContent ou lista de modelos)."""

    status = 200

    def __init__(self, texto="Resposta do modelo"):
        self.texto = texto

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({"candidates": [{"content": {"parts": [{"text": self.texto}]}}]}).encode("utf-8")


def erro_http(codigo):
    return urllib.error.HTTPError("https://exemplo", codigo, "erro", {}, None)


class BaseBD(unittest.TestCase):
    """Cada teste corre numa transação desfeita no fim (banco de teste isolado)."""

    def setUp(self):
        self._atomic = transaction.atomic()
        self._atomic.__enter__()
        self.addCleanup(self._desfazer)
        self.c = Client()

    def _desfazer(self):
        transaction.set_rollback(True)
        self._atomic.__exit__(None, None, None)

    def post_json(self, url, corpo):
        return self.c.post(url, data=json.dumps(corpo), content_type="application/json")


# ---------------------------------------------------------------- defeito 1
def colunas_em_falta(colunas_da_tabela):
    """Compara os campos dos models com as colunas reais. colunas_da_tabela(nome) -> set | None."""
    faltas = {}
    for app in ("recomendacao", "context_agent_datadriven"):
        for model in django_apps.get_app_config(app).get_models():
            tabela = model._meta.db_table
            existentes = colunas_da_tabela(tabela)
            esperadas = {f.column for f in model._meta.local_fields}
            falta = sorted(esperadas) if existentes is None else sorted(esperadas - existentes)
            if falta:
                faltas[tabela] = falta
    return faltas


# DDL das tabelas do agente no db.sqlite3 criado à mão (arquivado em archive/2026-09-27/).
DDL_ANTIGO = [
    "CREATE TABLE context_agent_datadriven_conversaagentesessao (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL, cliente_nome VARCHAR(150) NOT NULL, cliente_genero VARCHAR(1) NOT NULL, score_comportamental INTEGER NOT NULL, indice_corte VARCHAR(50) NOT NULL, iniciado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE context_agent_datadriven_mensagemagenteregistro (id INTEGER PRIMARY KEY AUTOINCREMENT, sessao_id INTEGER NOT NULL, papel VARCHAR(20) NOT NULL, conteudo TEXT NOT NULL, secret_utilizado VARCHAR(100) NOT NULL, tokens_estimados INTEGER DEFAULT 0, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
]


class EsquemaPorMigracoesTest(BaseBD):
    def test_banco_migrado_tem_todas_as_colunas_dos_models(self):
        def colunas(tabela):
            with connection.cursor() as cur:
                if tabela not in connection.introspection.table_names(cur):
                    return None
                return {c.name for c in connection.introspection.get_table_description(cur, tabela)}
        self.assertEqual(colunas_em_falta(colunas), {})

    def test_prova_negativa_esquema_antigo_feito_a_mao_reprova(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        cx = sqlite3.connect(str(Path(pasta.name) / "antigo.sqlite3"))
        self.addCleanup(cx.close)
        for ddl in DDL_ANTIGO:
            cx.execute(ddl)

        def colunas(tabela):
            linhas = cx.execute(f"PRAGMA table_info({tabela})").fetchall()
            return {linha[1] for linha in linhas} if linhas else None
        faltas = colunas_em_falta(colunas)
        self.assertIn("data_corte_fixa", faltas["context_agent_datadriven_conversaagentesessao"])
        self.assertIn("horario_casado", faltas["context_agent_datadriven_conversaagentesessao"])
        self.assertIn("horario_registro", faltas["context_agent_datadriven_mensagemagenteregistro"])

    def test_sem_migracoes_pendentes(self):
        # makemigrations --check sai com SystemExit(1) se um model divergir das migrações.
        call_command("makemigrations", "recomendacao", "context_agent_datadriven", check=True, dry_run=True, verbosity=0)

    def test_uma_sessao_por_cliente(self):
        ConversaAgenteSessao.objects.create(cliente_id=7)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ConversaAgenteSessao.objects.create(cliente_id=7)  # prova negativa: duplicado reprova
        self.assertEqual(ConversaAgenteSessao.objects.filter(cliente_id=7).count(), 1)

    def test_init_database_popula_sobre_o_esquema_migrado_sem_sobrescrever_a_chave(self):
        import init_database
        from apps.recomendacao.models import ClienteRegistro, PlanilhaProdutoRegistro
        init_database.popular()
        FeatureFlagInteracaoTelaIAI.objects.filter(pk="CHAVE_INTEIRACAO_TELA_IAI").update(chave_ativa=False)
        init_database.popular()  # idempotente
        self.assertEqual(ClienteRegistro.objects.count(), 1000)
        self.assertEqual(PlanilhaProdutoRegistro.objects.count(), 5)
        self.assertFalse(FeatureFlagInteracaoTelaIAI.objects.get(pk="CHAVE_INTEIRACAO_TELA_IAI").chave_ativa)


# ---------------------------------------------------------------- defeitos 1, 2 (rota descontinuada)
# Decisão D-3, 2026-09-27: enviar-mensagem/ responde 410 Gone e aponta conversas/interacao/. Os testes do
# comportamento antigo (200 com modelo, queda para o flash-lite, 503 de contingência, 400 por tipo) estão em
# archive/2026-09-27/tests/test_semantica_backend.py. Aqui os mesmos casos afirmam o comportamento decidido.
URL_ENVIAR = "/api/v1/context-agent/enviar-mensagem/"
GONE = {"erro": "rota_descontinuada", "usar": "/api/v1/context-agent/conversas/interacao/"}


class RotaDescontinuada:
    def assert_gone(self, r, abrir=None):
        self.assertEqual(r.status_code, 410, r.content)
        self.assertEqual(r.json(), GONE)
        if abrir is not None:
            abrir.assert_not_called()
        self.assertEqual(ConversaAgenteSessao.objects.count(), 0)
        self.assertEqual(MensagemAgenteRegistro.objects.count(), 0)


class EnviarMensagemTest(RotaDescontinuada, BaseBD):
    def test_modelo_responde_200_e_grava_par_na_mesma_sessao(self):
        # Decisão D-3, 2026-09-27: antes 200 e par gravado; agora 410 nas duas chamadas, sem modelo e sem gravar.
        with patch.dict(os.environ, COM_CHAVE), patch("urllib.request.urlopen", return_value=RespostaGoogle()) as abrir:
            r1 = self.post_json(URL_ENVIAR, {"mensagem": "quero investir", "cliente_id": 42})
            r2 = self.post_json(URL_ENVIAR, {"mensagem": "e o cartão?", "cliente_id": 42})
        self.assert_gone(r1, abrir)
        self.assert_gone(r2, abrir)

    def test_primario_falha_e_flash_lite_responde(self):
        # Decisão D-3, 2026-09-27: a queda de modelo desta rota deixou de existir (410 antes de chamar modelo).
        # A ordem de modelos da conversa nova (I2) é da f7 e é testada em apps/conversas, não aqui.
        respostas = [erro_http(429), RespostaGoogle("do lite")]
        with patch.dict(os.environ, COM_CHAVE), patch("urllib.request.urlopen", side_effect=respostas) as abrir:
            r = self.post_json(URL_ENVIAR, {"mensagem": "oi", "cliente_id": 5})
        self.assert_gone(r, abrir)

    def test_prova_negativa_sem_chave_nao_finge_sucesso(self):
        # Decisão D-3, 2026-09-27: sem chave também 410; nunca 200 nem sucesso.
        with patch.dict(os.environ, SEM_CHAVE), patch("urllib.request.urlopen") as abrir:
            r = self.post_json(URL_ENVIAR, {"mensagem": "quero investir", "cliente_id": 42})
        self.assert_gone(r, abrir)
        self.assertNotIn("sucesso", r.json())

    def test_todos_os_modelos_falham_com_chave_da_503_sem_expor_a_chave(self):
        # Decisão D-3, 2026-09-27: 410 e a chave não aparece na resposta.
        with patch.dict(os.environ, COM_CHAVE), patch("urllib.request.urlopen", side_effect=erro_http(403)) as abrir:
            r = self.post_json(URL_ENVIAR, {"mensagem": "oi", "cliente_id": 9})
        self.assert_gone(r, abrir)
        self.assertNotIn(CHAVE_TESTE, r.content.decode("utf-8"))

    def test_prova_negativa_modelo_vaza_score_e_resposta_e_bloqueada(self):
        # Decisão D-3, 2026-09-27: o modelo que vazaria o score nem é chamado.
        with patch.dict(os.environ, COM_CHAVE), patch("urllib.request.urlopen", return_value=RespostaGoogle("score: 187")) as abrir:
            r = self.post_json(URL_ENVIAR, {"mensagem": "qual é meu fluxo?", "cliente_id": 1})
        self.assert_gone(r, abrir)
        self.assertNotIn("score: 187", r.content.decode("utf-8"))

    def test_prova_negativa_resposta_antiga_reprova(self):
        # Decisão D-3, 2026-09-27. Prova negativa: o 503 de contingência antigo reprova no assert_gone.
        antiga = type("R", (), {"status_code": 503, "content": b"{}", "json": lambda self: {"origem_resposta": "contingencia"}})()
        with self.assertRaises(AssertionError):
            self.assert_gone(antiga)


# ---------------------------------------------------------------- defeito 5 (rota descontinuada)
class EnviarMensagemTiposTest(RotaDescontinuada, BaseBD):
    RUINS = [
        ("cliente_id nao numerico", {"mensagem": "oi", "cliente_id": "abc"}),
        ("cliente_id booleano", {"mensagem": "oi", "cliente_id": True}),
        ("cliente_id decimal", {"mensagem": "oi", "cliente_id": 4.5}),
        ("contexto nao objeto", {"mensagem": "oi", "cliente_id": 45, "contexto": "x"}),
        ("contexto.score texto", {"mensagem": "oi", "contexto": {"score": "alto"}}),
        ("mensagem nao texto", {"mensagem": 123}),
        ("mensagem ausente", {"cliente_id": 42}),
        ("mensagem so espacos", {"mensagem": "   "}),
        ("score texto", {"mensagem": "oi", "score": "750"}),
        ("cliente_nome numero", {"mensagem": "oi", "cliente_nome": 7}),
    ]

    def test_prova_negativa_tipos_errados_dao_400_com_erro(self):
        # Decisão D-3, 2026-09-27: o corpo não é mais lido; tipo errado recebe o mesmo 410 (nunca 500).
        with patch.dict(os.environ, SEM_CHAVE):
            for nome, corpo in self.RUINS:
                with self.subTest(nome):
                    self.assert_gone(self.post_json(URL_ENVIAR, corpo))

    def test_corpo_nao_objeto_da_400(self):
        # Decisão D-3, 2026-09-27: 410 também para corpo que não é objeto.
        self.assert_gone(self.post_json(URL_ENVIAR, ["oi"]))

    def test_tipos_certos_continuam_aceites(self):
        # Decisão D-3, 2026-09-27: corpo válido também recebe 410, e o modelo não é chamado.
        with patch.dict(os.environ, COM_CHAVE), patch("urllib.request.urlopen", return_value=RespostaGoogle()) as abrir:
            for corpo in ({"mensagem": "oi", "cliente_id": "43", "score": 400},
                          {"mensagem": "oi", "contexto": {"nome": "Maria", "score": 600.5}},
                          {"mensagem": "reserva"}):
                with self.subTest(corpo=corpo):
                    self.assert_gone(self.post_json(URL_ENVIAR, corpo), abrir)


# ---------------------------------------------------------------- defeito 3
URL_CHAVE = "/api/v1/chave-interacao-tela-iai/"


class ChaveInteracaoTest(BaseBD):
    def estado(self):
        return self.c.get(URL_CHAVE).json()["chave_ativa"]

    def test_booleanos_gravam_e_sao_relidos(self):
        r = self.post_json(URL_CHAVE, {"chave_ativa": False})
        self.assertEqual(r.status_code, 200)
        self.assertIs(r.json()["chave_ativa"], False)
        self.assertIs(self.estado(), False)
        self.assertIs(self.post_json(URL_CHAVE, {"chave_ativa": True}).json()["chave_ativa"], True)
        self.assertIs(self.estado(), True)

    def test_ausencia_alterna(self):
        antes = self.estado()
        r = self.post_json(URL_CHAVE, {})
        self.assertEqual(r.status_code, 200)
        self.assertIs(self.estado(), not antes)

    def test_prova_negativa_texto_false_nao_liga_a_chave(self):
        self.post_json(URL_CHAVE, {"chave_ativa": False})
        for valor in ("false", "true", 0, 1, None, [], {}):
            with self.subTest(valor=valor):
                r = self.post_json(URL_CHAVE, {"chave_ativa": valor})
                self.assertEqual(r.status_code, 400, r.content)
                self.assertEqual(set(r.json()), {"erro"})
        self.assertIs(self.estado(), False)  # nada mudou

    def test_prova_negativa_falha_de_gravacao_nao_diz_sucesso(self):
        with patch("apps.recomendacao.services.template_engine.TemplateEngine.set_chave_interacao_tela_iai", return_value=False):
            r = self.post_json(URL_CHAVE, {"chave_ativa": False})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(set(r.json()), {"erro"})
        self.assertNotIn("sucesso", r.content.decode("utf-8"))


# ---------------------------------------------------------------- defeito 4
URL_STATUS = "/api/v1/context-agent/status-harness/"


def status_chave(resposta):
    return resposta.json()["llm_models_provedores"]["secret_gsconsole"]


class StatusHarnessTest(BaseBD):
    def test_sem_chave_ausente_e_sem_rede_mesmo_com_validar(self):
        with patch.dict(os.environ, SEM_CHAVE), patch("urllib.request.urlopen") as abrir:
            s = status_chave(self.c.get(URL_STATUS))
            s2 = status_chave(self.c.get(URL_STATUS + "?validar=1"))
        abrir.assert_not_called()
        self.assertEqual(s["status"], "AUSENTE")
        self.assertEqual(s2["status"], "AUSENTE")
        self.assertFalse(s2["validacao"]["executada"])

    def test_prova_negativa_chave_presente_sem_validar_nao_diz_conectado(self):
        with patch.dict(os.environ, COM_CHAVE), patch("urllib.request.urlopen") as abrir:
            r = self.c.get(URL_STATUS)
        abrir.assert_not_called()
        s = status_chave(r)
        self.assertEqual(s["status"], "CONFIGURADA")
        self.assertNotIn("CONECTADO", r.content.decode("utf-8"))
        self.assertNotIn(CHAVE_TESTE, r.content.decode("utf-8"))

    def test_chave_curta_tambem_e_configurada_e_nao_vaza(self):
        with patch.dict(os.environ, {**SEM_CHAVE, "API_KEY_SECRECT": "abc123"}):
            r = self.c.get(URL_STATUS)
        self.assertEqual(status_chave(r)["status"], "CONFIGURADA")
        self.assertNotIn("abc123", r.content.decode("utf-8"))

    def test_validar_200_validada_com_chave_no_header_e_nao_na_url(self):
        with patch.dict(os.environ, COM_CHAVE), patch("urllib.request.urlopen", return_value=RespostaGoogle()) as abrir:
            r = self.c.get(URL_STATUS + "?validar=1")
        req = abrir.call_args.args[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.get_header("X-goog-api-key"), CHAVE_TESTE)
        self.assertNotIn(CHAVE_TESTE, req.full_url)
        self.assertLessEqual(abrir.call_args.kwargs["timeout"], 10)
        s = status_chave(r)
        self.assertEqual(s["status"], "VALIDADA")
        self.assertEqual(s["validacao"]["http_status"], 200)
        self.assertNotIn(CHAVE_TESTE, r.content.decode("utf-8"))

    def test_prova_negativa_google_recusa_invalida(self):
        for codigo in (400, 401, 403):
            with self.subTest(codigo=codigo):
                with patch.dict(os.environ, COM_CHAVE), patch("urllib.request.urlopen", side_effect=erro_http(codigo)):
                    s = status_chave(self.c.get(URL_STATUS + "?validar=1"))
                self.assertEqual(s["status"], "INVALIDA")

    def test_erro_de_rede_diz_que_nao_mediu(self):
        for erro in (urllib.error.URLError("sem rede"), TimeoutError(), erro_http(429), erro_http(503)):
            with self.subTest(erro=repr(erro)):
                with patch.dict(os.environ, COM_CHAVE), patch("urllib.request.urlopen", side_effect=erro):
                    s = status_chave(self.c.get(URL_STATUS + "?validar=1"))
                self.assertEqual(s["status"], "NAO_MEDIDO")
                self.assertTrue(s["validacao"]["executada"])


AFIRMACOES_SEM_MEDIDA = ("CONECTADO", "Autenticado & Operacional", "status-secret")


def afirmacoes_sem_medida(html):
    return [t for t in AFIRMACOES_SEM_MEDIDA if t in html]


class PainelTest(BaseBD):
    def test_painel_nao_afirma_o_que_nao_mediu(self):
        with patch.dict(os.environ, COM_CHAVE), patch("urllib.request.urlopen") as abrir:
            html = self.c.get("/context-agent/").content.decode("utf-8")
        abrir.assert_not_called()
        self.assertEqual(afirmacoes_sem_medida(html), [])
        self.assertIn("CONFIGURADA", html)
        self.assertNotIn("{{ESTADO_CHAVE}}", html)

    def test_prova_negativa_painel_antigo_reprova(self):
        antigo = '<span>Secret: CONECTADO</span><p>Autenticado & Operacional</p>'
        self.assertEqual(afirmacoes_sem_medida(antigo), ["CONECTADO", "Autenticado & Operacional"])
        self.assertEqual(afirmacoes_sem_medida(HTML_PAINEL), [])


# ---------------------------------------------------------------- defeito 6
ROTAS_API_CLIENTE = ["/api/v1/cliente/%d/", "/api/v1/chat/variavel-1/%d/",
                     "/api/v1/comunicacao/e-agora/%d/", "/api/v1/contexto-score/%d/"]
ROTAS_HTML_CLIENTE = ["/app/chat/%d/", "/app/comunicacao/%d/"]


class IdsForaDoRecorteTest(BaseBD):
    def test_prova_negativa_1042_nao_vira_42(self):
        for rota in ROTAS_API_CLIENTE:
            for cid in (1042, 1001, 0):
                with self.subTest(rota=rota, cid=cid):
                    r = self.c.get(rota % cid)
                    self.assertEqual(r.status_code, 404, r.content)
                    self.assertEqual(set(r.json()), {"erro"})
        for rota in ROTAS_HTML_CLIENTE:
            with self.subTest(rota=rota):
                self.assertEqual(self.c.get(rota % 1042).status_code, 404)
        self.assertEqual(self.c.get("/app/?cliente_id=1042").status_code, 404)
        self.assertEqual(self.c.get("/app/?cliente_id=abc").status_code, 404)

    def test_limites_do_recorte_respondem_com_o_id_pedido(self):
        for cid in (1, 42, 1000):
            with self.subTest(cid=cid):
                r = self.c.get("/api/v1/chat/variavel-1/%d/" % cid)
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json()["cliente"]["id"], cid)
                self.assertEqual(self.c.get("/api/v1/cliente/%d/" % cid).json()["id"], cid)
                self.assertEqual(self.c.get("/app/chat/%d/" % cid).status_code, 200)


if __name__ == "__main__":
    unittest.main()
