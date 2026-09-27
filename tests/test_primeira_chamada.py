import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.context_agent_datadriven.services.primeira_chamada import chamar_gemini
from desafio_itau.segredos import obter_api_key

SEM_CHAVE = {
    "API_KEY_SECRECT": "",
    "GEMINI_API_KEY": "",
    "GSCONSOLE_SECRET": "",
    "GOOGLE_API_KEY": "",
    "SECRETS_FILE": str(Path(tempfile.gettempdir()) / "nao-existe" / ".secrets"),
}


class Resposta:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"candidates":[{"content":{"parts":[{"text":"Resposta"}]}}]}'


class PrimeiraChamadaTest(unittest.TestCase):
    def test_envia_somente_texto_inicial(self):
        with patch.dict(os.environ, {**SEM_CHAVE, "GEMINI_API_KEY": "chave-de-teste"}):
            with patch("urllib.request.urlopen", return_value=Resposta()) as abrir:
                resultado = chamar_gemini("Olá")

        requisicao = abrir.call_args.args[0]
        self.assertEqual(
            json.loads(requisicao.data),
            {"contents": [{"role": "user", "parts": [{"text": "Olá"}]}]},
        )
        self.assertEqual(requisicao.get_header("X-goog-api-key"), "chave-de-teste")
        self.assertEqual(resultado["resposta"], "Resposta")

    def test_sem_chave_nao_chama_google(self):
        with patch.dict(os.environ, SEM_CHAVE):
            with patch("urllib.request.urlopen") as abrir:
                resultado = chamar_gemini("Olá")
        self.assertFalse(resultado["sucesso"])
        self.assertIn("API_KEY_SECRECT", resultado["erro"])
        abrir.assert_not_called()


class SegredosTest(unittest.TestCase):
    def _arquivo(self, conteudo):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        caminho = Path(pasta.name) / ".secrets"
        caminho.write_text(conteudo, encoding="utf-8")
        return str(caminho)

    def test_le_api_key_secrect_do_arquivo_secrets(self):
        arquivo = self._arquivo('# chave do agente\nAPI_KEY_SECRECT="chave-do-arquivo"\n')
        with patch.dict(os.environ, {**SEM_CHAVE, "SECRETS_FILE": arquivo}):
            self.assertEqual(obter_api_key(), ("chave-do-arquivo", ".secrets:API_KEY_SECRECT"))
            with patch("urllib.request.urlopen", return_value=Resposta()) as abrir:
                chamar_gemini("Olá")
        self.assertEqual(abrir.call_args.args[0].get_header("X-goog-api-key"), "chave-do-arquivo")

    def test_ambiente_vence_arquivo(self):
        arquivo = self._arquivo("API_KEY_SECRECT=chave-do-arquivo\n")
        with patch.dict(os.environ, {**SEM_CHAVE, "SECRETS_FILE": arquivo, "API_KEY_SECRECT": "chave-do-env"}):
            self.assertEqual(obter_api_key(), ("chave-do-env", "env:API_KEY_SECRECT"))

    def test_arquivo_vence_legado(self):
        arquivo = self._arquivo("API_KEY_SECRECT=chave-do-arquivo\n")
        with patch.dict(os.environ, {**SEM_CHAVE, "SECRETS_FILE": arquivo, "GEMINI_API_KEY": "legado"}):
            self.assertEqual(obter_api_key()[0], "chave-do-arquivo")

    def test_prova_negativa_arquivo_sem_chave_nao_chama_google(self):
        arquivo = self._arquivo("# API_KEY_SECRECT=comentada\n\nOUTRA_CHAVE=x\nAPI_KEY_SECRECT=\n")
        with patch.dict(os.environ, {**SEM_CHAVE, "SECRETS_FILE": arquivo}):
            self.assertEqual(obter_api_key(), (None, None))
            with patch("urllib.request.urlopen") as abrir:
                resultado = chamar_gemini("Olá")
        self.assertFalse(resultado["sucesso"])
        abrir.assert_not_called()


if __name__ == "__main__":
    unittest.main()
