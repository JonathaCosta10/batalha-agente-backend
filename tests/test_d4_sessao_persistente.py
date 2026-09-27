"""Decisão D-4, 2026-09-27: a sessão de perfil-usuario sobrevive ao reinício do processo e expira em 4 h.

Armazenamento: model SessaoPerfilUsuario (SQLite, migração 0002), no lugar do dict em memória.
"Reinício" aqui = descartar todo o estado em memória do módulo services/perfil_usuario.py (armazém de sessões
e cache do CSV) e ler de novo. Relógio simulado por `pu._relogio`.

Provas negativas:
- o mesmo "reinício" aplicado ao armazenamento antigo (dict em memória) PERDE a sessão: o teste sabe distinguir;
- sessão expirada devolve 404 na rota perfil-usuario/pergunta/, sem chamar modelo.
O banco é o de teste em memória, criado pelas migrações (não toca no db.sqlite3).
"""

import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")
import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import setup_databases, setup_test_environment, teardown_databases, teardown_test_environment  # noqa: E402

from apps.context_agent_datadriven.models import SessaoPerfilUsuario  # noqa: E402
from apps.context_agent_datadriven.services import perfil_usuario as pu  # noqa: E402

MARIA = "00108ccd-699c-453a-a9f9-a66aad6e03e5"
CSV = ("indice,id_usuario,nome,genero,movimentos,meses,primeiro_anomes,ultimo_anomes\n"
       f"1,{MARIA},Maria,F,433,12,202501,202512\n")
T0 = 1_790_000_000.0

_estado_bd = None


def setUpModule():
    global _estado_bd
    logging.getLogger("django.request").setLevel(logging.ERROR)
    setup_test_environment()
    _estado_bd = setup_databases(verbosity=0, interactive=False)


def tearDownModule():
    teardown_databases(_estado_bd, verbosity=0)
    teardown_test_environment()


def reiniciar_processo():
    """Descarta o estado em memória do módulo, como um runserver novo: armazém novo e cache do CSV vazio."""
    pu._sessoes = type(pu._sessoes)()
    pu._base.update({"mtime": None, "por_indice": {}, "por_uuid": {}})


class SessaoPersistenteTest(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        csv = Path(pasta.name) / "usuarios_verdade.csv"
        csv.write_text(CSV, encoding="utf-8")
        self.relogio = [T0]
        for alvo, valor in (("ARQUIVO_CSV", csv), ("_relogio", lambda: self.relogio[0])):
            p = mock.patch.object(pu, alvo, valor)
            p.start()
            self.addCleanup(p.stop)
        armazem_original = pu._sessoes
        self.addCleanup(setattr, pu, "_sessoes", armazem_original)
        pu._base["mtime"] = None
        SessaoPerfilUsuario.objects.all().delete()

    def test_sessao_sobrevive_ao_reinicio(self):
        sid = pu.definir_usuario(MARIA)["sessao_id"]
        reiniciar_processo()
        self.assertEqual(pu.usuario_da_sessao(sid)["codigo"], MARIA)
        with connection.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM context_agent_datadriven_sessaoperfilusuario WHERE sessao_id = %s", [sid])
            self.assertEqual(cur.fetchone()[0], 1)

    def test_prova_negativa_armazem_em_memoria_perde_a_sessao_no_reinicio(self):
        """O armazenamento anterior à D-4 (dict do processo) reprova no mesmo teste de reinício."""
        pu._sessoes = {}
        # Grava à moda antiga (dict do processo), como definir_usuario fazia antes da D-4.
        sid = "a" * 32
        pu._sessoes[sid] = {"usuario": pu.identificar(MARIA), "criada": self.relogio[0]}
        self.assertEqual(pu.usuario_da_sessao(sid)["codigo"], MARIA)
        reiniciar_processo()
        with self.assertRaises(pu.SessaoNaoEncontrada):
            pu.usuario_da_sessao(sid)

    def test_ttl_4h_com_relogio_simulado(self):
        self.assertEqual(pu.SESSAO_SEGUNDOS, 4 * 60 * 60)
        sid = pu.definir_usuario(MARIA)["sessao_id"]
        self.relogio[0] = T0 + pu.SESSAO_SEGUNDOS
        reiniciar_processo()
        self.assertEqual(pu.usuario_da_sessao(sid)["codigo"], MARIA)  # no limite ainda vale
        self.relogio[0] = T0 + pu.SESSAO_SEGUNDOS + 1
        with self.assertRaises(pu.SessaoNaoEncontrada):
            pu.usuario_da_sessao(sid)
        self.assertFalse(SessaoPerfilUsuario.objects.filter(sessao_id=sid).exists())  # a vencida é apagada

    def test_definir_expurga_sessoes_vencidas(self):
        velha = pu.definir_usuario(MARIA)["sessao_id"]
        self.relogio[0] = T0 + pu.SESSAO_SEGUNDOS + 1
        nova = pu.definir_usuario(MARIA)["sessao_id"]
        self.assertEqual(list(SessaoPerfilUsuario.objects.values_list("sessao_id", flat=True)), [nova])
        self.assertNotEqual(velha, nova)

    def test_prova_negativa_sessao_expirada_da_404_sem_chamar_modelo(self):
        http = Client()
        r = http.post("/api/v1/context-agent/perfil-usuario/definir/", {"usuario": MARIA}, content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content)
        sid = r.json()["sessao_id"]
        self.relogio[0] = T0 + pu.SESSAO_SEGUNDOS + 1
        reiniciar_processo()
        with mock.patch.object(pu.GoogleLLMCliente, "executar_chamada") as modelo:
            r = http.post("/api/v1/context-agent/perfil-usuario/pergunta/",
                          {"sessao_id": sid, "pergunta": "quem sou eu?"}, content_type="application/json")
        self.assertEqual(r.status_code, 404, r.content)
        self.assertIn("sessao_id", r.json()["erro"])
        modelo.assert_not_called()


if __name__ == "__main__":
    unittest.main()
