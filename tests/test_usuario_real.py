"""Rotas /api/v1/context-agent/usuario-real/ com executor falso (sem rede, sem BigQuery).

Provas negativas: fonte OFF responde 503 e não consulta; UUID inexistente 404; índice fora 404;
referência lixo 400; tópico e categoria fora do catálogo 422; BigQuery que falha 503 NAO_MEDIDO.
"""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")
import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.test import Client, override_settings  # noqa: E402

from apps.context_agent_datadriven.services import usuario_real  # noqa: E402

UUIDS = ["00108ccd-699c-453a-a9f9-a66aad6e03e5", "001221d1-3626-45c1-807a-990502adf808"]
BASE = "/api/v1/context-agent/usuario-real/"


class ExecutorFalso:
    chamadas = []

    def executar(self, sql, parametros):
        ExecutorFalso.chamadas.append(parametros)
        self.ultimo_job = {"job_id": f"job-{len(ExecutorFalso.chamadas)}", "bytes_processados": 10}
        if "ROW_NUMBER" in sql:
            return [{"indice": i + 1, "id_usuario": u, "movimentos": 400, "meses": 12,
                     "primeiro_anomes": 202501, "ultimo_anomes": 202512} for i, u in enumerate(UUIDS)]
        if "segmento_t3" in sql:
            return [{"meses": 11, "inflow_mensal": 5000.0, "outflow_mensal": 4500.0, "surplus_mensal": 500.0,
                     "taxa_surplus_pct": 10.0, "saidas_sem_grupo": 0, "segmento_t3": "Esbanjador"}]
        return [{"valor": 1.0}]


class ExecutorQuebrado:
    def executar(self, sql, parametros):
        raise ConnectionError("sem ADC")


class UsuarioRealTest(unittest.TestCase):
    def setUp(self):
        usuario_real.cache.limpar()
        ExecutorFalso.chamadas = []
        self.executor = patch.object(usuario_real, "_novo_executor", ExecutorFalso)
        self.executor.start()
        self.addCleanup(self.executor.stop)
        self.client = Client()

    def test_lista_paginada_com_selo(self):
        r = self.client.get(BASE + "?limite=1&offset=1")
        self.assertEqual(r.status_code, 200)
        corpo = r.json()
        self.assertEqual(corpo["total"], 2)
        self.assertEqual([u["id_usuario"] for u in corpo["usuarios"]], [UUIDS[1]])
        self.assertEqual(corpo["selo"]["fonte"], settings.USUARIO_REAL["TABELA"])

    def test_perfil_por_indice_e_por_uuid_e_o_mesmo(self):
        por_indice = self.client.get(BASE + "2/").json()
        por_uuid = self.client.get(BASE + UUIDS[1].upper() + "/").json()
        self.assertEqual(por_indice["usuario"]["id_usuario"], UUIDS[1])
        self.assertEqual(por_uuid["usuario"]["indice"], 2)
        self.assertEqual(por_indice["resumo"]["segmento_t3"], "Esbanjador")
        self.assertEqual(set(por_indice["visoes"]), set(usuario_real.TOPICOS_PERFIL))
        self.assertTrue(por_uuid["selo"]["cache"])  # segunda leitura do mesmo UUID não consulta de novo

    def test_visao_categoria_passa_a_grafia_da_base(self):
        r = self.client.get(BASE + "1/visao/categoria/?categoria=delivery")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["parametros"]["categoria"], "Delivery")

    def test_pergunta_roteia_para_uma_visao(self):
        r = self.client.post(BASE + "1/pergunta/", {"pergunta": "Quanto gasto com assinatura?"},
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["topico"], "recorrencias")

    # --- provas negativas ---------------------------------------------------------------

    def test_fonte_off_responde_503_sem_consultar(self):
        with override_settings(USUARIO_REAL={**settings.USUARIO_REAL, "ATIVO": False}):
            r = self.client.get(BASE + "1/")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["estado"], "OFF")
        self.assertEqual(ExecutorFalso.chamadas, [])

    def test_referencias_ruins(self):
        self.assertEqual(self.client.get(BASE + "3/").status_code, 404)
        self.assertEqual(self.client.get(BASE + "0/").status_code, 404)
        self.assertEqual(self.client.get(BASE + "ffffffff-ffff-ffff-ffff-ffffffffffff/").status_code, 404)
        self.assertEqual(self.client.get(BASE + "maria/").status_code, 400)
        self.assertEqual(self.client.get(BASE + "1/?data_corte=ontem").status_code, 400)

    def test_fora_do_catalogo_422(self):
        self.assertEqual(self.client.get(BASE + "1/visao/horoscopo/").status_code, 422)
        self.assertEqual(self.client.get(BASE + "1/visao/categoria/?categoria=Cassino").status_code, 422)
        r = self.client.post(BASE + "1/pergunta/", {"pergunta": "qual a cor do céu?"},
                             content_type="application/json")
        self.assertEqual(r.status_code, 422)

    def test_bigquery_indisponivel_503_nao_medido(self):
        with patch.object(usuario_real, "_novo_executor", ExecutorQuebrado):
            r = self.client.get(BASE + "1/")
            status_validado = self.client.get(BASE + "status/?validar=1").json()
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["estado"], "NAO_MEDIDO")
        self.assertEqual(status_validado["conexao"], "FALHOU")

    def test_saldo_mes_negativado_pelo_mes_do_corte(self):
        from datetime import date
        s = usuario_real.montar_saldo_mes({"lancamentos": 40, "entradas": 5000.0, "saidas": 5380.0},
                                          date(2025, 12, 22), {"surplus_mensal": 120.0})
        self.assertEqual((s["saldo"], s["negativado"], s["negativado_na_media"]), (-380.0, True, False))
        self.assertEqual(s["periodo"], {"de": "2025-12-01", "ate": "2025-12-22", "rotulo": "até 22/12/2025"})

    # prova negativa: saldo positivo não é negativado; média sem medição não vira False
    def test_saldo_mes_positivo_e_media_nao_medida(self):
        from datetime import date
        s = usuario_real.montar_saldo_mes({"lancamentos": 0, "entradas": None, "saidas": None},
                                          date(2025, 12, 22), {})
        self.assertEqual((s["saldo"], s["negativado"], s["negativado_na_media"]), (0.0, False, "NAO_MEDIDO"))

    def test_saldo_mes_bigquery_indisponivel_503(self):
        with patch.object(usuario_real, "_novo_executor", ExecutorQuebrado):
            r = self.client.get(BASE + "1/saldo-mes/")
        self.assertEqual((r.status_code, r.json()["estado"]), (503, "NAO_MEDIDO"))


if __name__ == "__main__":
    unittest.main()
