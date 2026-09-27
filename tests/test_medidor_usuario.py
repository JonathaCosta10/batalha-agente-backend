"""O medidor não pode aprovar saldos incompatíveis ou fatos após o corte."""

import importlib.util
import unittest
from datetime import date
from pathlib import Path


ARQUIVO = Path(__file__).resolve().parents[1] / "docs/estudo-i-agora/sql/medir_usuario.py"
spec = importlib.util.spec_from_file_location("medir_usuario", ARQUIVO)
modulo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modulo)


class MedidorUsuarioTest(unittest.TestCase):
    def setUp(self):
        self.fatos = {
            "total_movimentos": 2,
            "movimentos_entrada": 1,
            "movimentos_saida": 1,
            "entradas_total": 100.0,
            "saidas_total": 60.0,
            "saldo_periodo": 40.0,
            "ultima_movimentacao": "2025-12-22T12:00:00+00:00",
            "meses": [{"movimentos": 2, "entradas": 100.0, "saidas": 60.0}],
        }

    def test_medicao_coerente(self):
        self.assertTrue(all(modulo.checar_fatos(self.fatos, date(2025, 12, 22)).values()))

    def test_prova_negativa_saldo_inventado_reprova(self):
        self.fatos["saldo_periodo"] = 80.0
        self.assertFalse(modulo.checar_fatos(self.fatos, date(2025, 12, 22))["saldo_consistente"])

    def test_prova_negativa_apos_corte_reprova(self):
        self.fatos["ultima_movimentacao"] = "2025-12-23T12:00:00+00:00"
        self.assertFalse(modulo.checar_fatos(self.fatos, date(2025, 12, 22))["respeita_corte"])
