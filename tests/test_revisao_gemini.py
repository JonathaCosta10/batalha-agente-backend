"""scripts/revisao_gemini.py sem rede: sem chave não chama nada; caminhos relativos; verificador ligado."""

import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("revisao_gemini", RAIZ / "scripts" / "revisao_gemini.py")
revisao_gemini = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(revisao_gemini)

EXEMPLO = RAIZ / ".claude" / "skills" / "revisao-gemini" / "examples"


class RevisaoGeminiTest(unittest.TestCase):
    def test_sem_chave_nao_chama_e_sai_2(self):
        argv = ["revisao_gemini.py", "--titulo", "t", str(RAIZ / "README.md")]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(revisao_gemini, "obter_api_key", return_value=("", None)), \
                mock.patch.object(revisao_gemini, "chamar") as chamar, redirect_stdout(io.StringIO()) as saida:
            codigo = revisao_gemini.main()
        self.assertEqual(codigo, 2)
        chamar.assert_not_called()
        self.assertIn("NAO_MEDIDO", saida.getvalue())

    def test_selo_usa_caminho_relativo_a_raiz(self):
        _, selos = revisao_gemini.montar("t", [RAIZ / "README.md"])
        self.assertEqual(selos[0]["arquivo"], "README.md")

    def test_modelo_vem_da_fonte_unica(self):
        from desafio_itau.modelos_llm import MODELO_PRIMEIRA_CHAMADA
        self.assertEqual(revisao_gemini.MODELO, MODELO_PRIMEIRA_CHAMADA)

    @unittest.skipUnless((EXEMPLO / "revisao-sintetica.json").is_file(), "skill revisao-gemini ausente (.claude local)")
    def test_verificador_aprova_exemplo_e_reprova_adulterado(self):
        verificar = revisao_gemini.verificador().verificar
        exemplo = json.loads((EXEMPLO / "revisao-sintetica.json").read_text(encoding="utf-8"))
        self.assertEqual(verificar(exemplo), [])
        exemplo["papel"] = "aprovador"
        self.assertTrue(any("papel" in f for f in verificar(exemplo)))


if __name__ == "__main__":
    unittest.main()
