"""Prova positiva e negativa do guard BigQuery com consultor local injetado."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from base import Recusa, contrato, validar_linha
from preparar_extracao import preparar
from validar_resposta import validar

USUARIO = "123e4567-e89b-42d3-a456-426614174000"
LINHA = {
    "anomesdia": "2025-08-05T12:00:00+00:00", "anomes": 202508,
    "tipo": "S", "vlr": 25.5, "nom_cate_macro": "Mercado",
}


class ConsultorFalso:
    def __init__(self, linhas=None):
        self.linhas = [dict(LINHA)] if linhas is None else linhas
        self.jobs = []

    def usuarios(self):
        self.jobs.append({"job_id": "teste-usuarios", "bytes_processados": 1})
        return [USUARIO]

    def movimentos(self, id_usuario):
        assert id_usuario == USUARIO
        self.jobs.append({"job_id": "teste-movimentos", "bytes_processados": 1})
        return [validar_linha(dict(linha), contrato()) for linha in self.linhas]


class ConsultorIndisponivel(ConsultorFalso):
    def movimentos(self, id_usuario):
        raise RuntimeError("BigQuery indisponível no teste")


class ExtracaoIAITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "evidencias")
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.evidencia = self.raiz / "clique.json"
        self.proposta = self.raiz / "proposta.json"

    def preparar(self):
        esperada = preparar(self.evidencia, ConsultorFalso())["proposta_esperada"]
        self.proposta.write_text(json.dumps(esperada), encoding="utf-8")
        return esperada

    def test_aprovacao_e_evidencia(self):
        esperada = self.preparar()
        liberada = validar(self.evidencia, self.proposta, ConsultorFalso())
        self.assertTrue(liberada["aprovado"])
        self.assertIn(str(esperada["valor"]), liberada["resposta"])
        registro = json.loads(self.evidencia.read_text(encoding="utf-8"))
        self.assertEqual(registro["estado"], "APROVADO")
        self.assertEqual(len(registro["consultas"]["jobs"]), 2)
        self.assertEqual(len(registro["guard"]["jobs"]), 2)

    def test_fato_inventado_reprovado(self):
        esperada = self.preparar()
        esperada["valor"] = "99% garantidos"
        self.proposta.write_text(json.dumps(esperada), encoding="utf-8")
        with self.assertRaisesRegex(Recusa, "fato diferente"):
            validar(self.evidencia, self.proposta, ConsultorFalso())
        self.assertEqual(json.loads(self.evidencia.read_text(encoding="utf-8"))["estado"], "REPROVADO")

    def test_chave_extra_reprovada(self):
        esperada = self.preparar()
        esperada["afirmacao_livre"] = "aprovado"
        self.proposta.write_text(json.dumps(esperada), encoding="utf-8")
        with self.assertRaisesRegex(Recusa, "estrutura JSON"):
            validar(self.evidencia, self.proposta, ConsultorFalso())

    def test_numero_do_usuario_inventado_reprovado(self):
        esperada = self.preparar()
        esperada["numero_usuario"] = 99
        self.proposta.write_text(json.dumps(esperada), encoding="utf-8")
        with self.assertRaisesRegex(Recusa, "fato diferente"):
            validar(self.evidencia, self.proposta, ConsultorFalso())

    def test_numero_da_evidencia_trocado_reprovado(self):
        self.preparar()
        registro = json.loads(self.evidencia.read_text(encoding="utf-8"))
        registro["selecao"]["numero_usuario"] = 2
        self.evidencia.write_text(json.dumps(registro), encoding="utf-8")
        with self.assertRaisesRegex(Recusa, "número do sorteio"):
            validar(self.evidencia, self.proposta, ConsultorFalso())

    def test_linha_alterada_reprovada(self):
        self.preparar()
        alterada = dict(LINHA, vlr=30.0, nom_cate_macro="Outra")
        with self.assertRaisesRegex(Recusa, "divergiu"):
            validar(self.evidencia, self.proposta, ConsultorFalso([alterada]))

    def test_falha_de_consulta_e_nao_medido(self):
        self.preparar()
        with self.assertRaisesRegex(Recusa, "BigQuery indisponível"):
            validar(self.evidencia, self.proposta, ConsultorIndisponivel())
        self.assertEqual(json.loads(self.evidencia.read_text(encoding="utf-8"))["estado"], "NAO_MEDIDO")

    def test_campo_nulo_reprovado_sem_normalizacao(self):
        alterada = dict(LINHA, nom_cate_macro=None)
        with self.assertRaisesRegex(Recusa, "categoria ausente"):
            preparar(self.evidencia, ConsultorFalso([alterada]))


if __name__ == "__main__":
    unittest.main()
