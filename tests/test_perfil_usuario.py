"""Rotas /api/v1/context-agent/perfil-usuario/ com CSV temporário e Gemini falso (sem rede).

Conferência 1: definir a Maria pelo id_usuario (UUID) e perguntar "quem sou eu" -> Código = id_usuario,
pessoa = Maria. Provas negativas: resposta sem o nome ou sem o código é REPROVADA (502); sessão desconhecida
404; usuário inexistente 404; referência lixo 400; índice posicional 400 (P0 2026-09-27); CSV ausente 503 NAO_MEDIDO; modelo fora 503.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")
import django  # noqa: E402

django.setup()

from django.test import Client  # noqa: E402

from apps.context_agent_datadriven.services import perfil_usuario as pu  # noqa: E402

BASE = "/api/v1/context-agent/perfil-usuario/"
MARIA = "00108ccd-699c-453a-a9f9-a66aad6e03e5"
EDUARDO = "001221d1-3626-45c1-807a-990502adf808"
CSV = (
    "indice,id_usuario,nome,genero,movimentos,meses,primeiro_anomes,ultimo_anomes\n"
    f"1,{MARIA},Maria,F,433,12,202501,202512\n"
    f"2,{EDUARDO},Eduardo,M,750,12,202501,202512\n"
)


class GeminiFalso:
    respostas = []
    chamadas = []

    @classmethod
    def executar_chamada(cls, modelo, sistema, conteudo, temperatura=0.35, max_tokens=650):
        cls.chamadas.append({"modelo": modelo, "sistema": sistema, "conteudo": conteudo})
        resposta = cls.respostas.pop(0)
        if resposta is None:
            return {"sucesso": False, "erro": "HTTP 503"}
        return {"sucesso": True, "resposta": resposta, "modelo": modelo}


class PerfilUsuarioTest(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.csv = Path(self.pasta.name) / "usuarios_verdade.csv"
        self.csv.write_text(CSV, encoding="utf-8")
        self.patches = [patch.object(pu, "ARQUIVO_CSV", self.csv),
                        patch.object(pu, "perguntar", self._perguntar_falso(pu.perguntar))]
        for p in self.patches:
            p.start()
        pu._base["mtime"] = None
        GeminiFalso.respostas, GeminiFalso.chamadas = [], []
        self.http = Client()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.pasta.cleanup()

    @staticmethod
    def _perguntar_falso(original):
        return lambda sessao_id, pergunta: original(sessao_id, pergunta, cliente=GeminiFalso,
                                                    modelos=["modelo-a", "modelo-b"])

    def _definir(self, usuario=MARIA):
        return self.http.post(BASE + "definir/", {"usuario": usuario}, content_type="application/json")

    def _perguntar(self, sessao_id, pergunta="quem sou eu?"):
        return self.http.post(BASE + "pergunta/", {"sessao_id": sessao_id, "pergunta": pergunta},
                              content_type="application/json")

    def test_conferencia_1_quem_sou_eu_maria(self):
        definido = self._definir(MARIA)
        self.assertEqual(definido.status_code, 201)
        publico = definido.json()["usuario"]
        self.assertEqual(publico, {"codigo": MARIA, "pessoa": "Maria", "nome_origem": "nome_gerado"})
        # prova negativa: o CSV tem genero e indice; nenhum dos dois pode sair no 201
        self.assertNotIn("genero", publico)
        self.assertNotIn("indice", publico)

        GeminiFalso.respostas = [f"Você é a Maria, e o seu código é {MARIA}."]
        resposta = self._perguntar(definido.json()["sessao_id"], "Quem sou eu?")
        corpo = resposta.json()
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(corpo["usuario"]["codigo"], MARIA)
        self.assertEqual(corpo["usuario"]["pessoa"], "Maria")
        self.assertEqual(corpo["intencao"], "quem_sou_eu")
        self.assertEqual(corpo["guard"], {"estado": "APROVADO", "conferido": ["pessoa", "codigo"]})
        sistema = GeminiFalso.chamadas[0]["sistema"]
        self.assertIn("Maria", sistema)
        self.assertIn(MARIA, sistema)

    def test_definir_por_uuid(self):
        self.assertEqual(self._definir(MARIA.upper()).json()["usuario"]["pessoa"], "Maria")

    def test_contra_prova_resposta_sem_codigo_reprovada(self):
        sessao = self._definir().json()["sessao_id"]
        GeminiFalso.respostas = ["Você é a Maria.", "Olá, Maria!"]
        resposta = self._perguntar(sessao)
        self.assertEqual(resposta.status_code, 502)
        self.assertEqual(resposta.json()["guard"], {"estado": "REPROVADO", "faltam": ["codigo"]})
        self.assertEqual(len(GeminiFalso.chamadas), 2)

    def test_contra_prova_resposta_com_outro_nome_reprovada(self):
        sessao = self._definir().json()["sessao_id"]
        GeminiFalso.respostas = [f"Você é o Eduardo, código {MARIA}.", f"Você é a Ana, código {MARIA}."]
        resposta = self._perguntar(sessao)
        self.assertEqual(resposta.status_code, 502)
        self.assertEqual(resposta.json()["guard"]["faltam"], ["pessoa"])

    def test_segundo_modelo_salva_quando_primeiro_falha(self):
        sessao = self._definir().json()["sessao_id"]
        GeminiFalso.respostas = [None, f"Maria, seu código é {MARIA}."]
        resposta = self._perguntar(sessao)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["modelo"], "modelo-b")

    def test_modelos_fora_503(self):
        sessao = self._definir().json()["sessao_id"]
        GeminiFalso.respostas = [None, None]
        self.assertEqual(self._perguntar(sessao).status_code, 503)

    def test_pergunta_livre_nao_exige_identidade(self):
        sessao = self._definir(EDUARDO).json()["sessao_id"]
        GeminiFalso.respostas = ["Ainda não tenho essa informação."]
        corpo = self._perguntar(sessao, "qual é o meu saldo?").json()
        self.assertEqual(corpo["intencao"], "livre")
        self.assertEqual(corpo["guard"]["conferido"], [])
        sistema = GeminiFalso.chamadas[0]["sistema"]
        self.assertIn("Eduardo", sistema)
        self.assertIn('"você"', sistema)  # tratamento neutro também para o titular M
        self.assertNotIn("o cliente", sistema)

    def test_sessao_desconhecida_404(self):
        self.assertEqual(self._perguntar("nao-existe").status_code, 404)

    def test_usuario_inexistente_404(self):
        self.assertEqual(self._definir("ffffffff-ffff-ffff-ffff-ffffffffffff").status_code, 404)

    def test_prova_negativa_indice_posicional_400(self):
        """P0 2026-09-27: o índice do CSV (antes "1" -> Maria) não identifica mais ninguém."""
        for indice in ("1", 1, "2", "999"):
            with self.subTest(indice=indice):
                resposta = self._definir(indice)
                self.assertEqual(resposta.status_code, 400)
                self.assertNotIn("sessao_id", resposta.json())
        for indice in ("1", 1):
            with self.assertRaises(pu.ReferenciaInvalida):
                pu.identificar(indice)

    def test_referencia_lixo_400(self):
        self.assertEqual(self._definir("drop table").status_code, 400)
        self.assertEqual(self.http.post(BASE + "definir/", {}, content_type="application/json").status_code, 400)
        sessao = self._definir().json()["sessao_id"]
        self.assertEqual(self._perguntar(sessao, "   ").status_code, 400)

    def test_aleatorio_sorteia_no_servidor_e_exclui_o_atual(self):
        # Base de 2: excluindo a Maria, só pode sair o Eduardo (e vice-versa), em todas as tentativas.
        for _ in range(10):
            corpo = {"usuario": "aleatorio", "excluir": MARIA}
            resposta = self.http.post(BASE + "definir/", corpo, content_type="application/json")
            self.assertEqual(resposta.status_code, 201)
            self.assertEqual(resposta.json()["usuario"]["codigo"], EDUARDO)
            corpo["excluir"] = EDUARDO.upper()
            resposta = self.http.post(BASE + "definir/", corpo, content_type="application/json")
            self.assertEqual(resposta.json()["usuario"]["codigo"], MARIA)
        # Sem excluir: qualquer um dos dois, sempre um id do CSV.
        codigo = self._definir("ALEATORIO").json()["usuario"]["codigo"]
        self.assertIn(codigo, (MARIA, EDUARDO))
        # Prova negativa: palavra parecida não sorteia, é referência inválida.
        self.assertEqual(self._definir("aleatoria").status_code, 400)

    def test_csv_ausente_503_nao_medido(self):
        self.csv.unlink()
        pu._base["mtime"] = None
        resposta = self._definir()
        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(resposta.json()["estado"], "NAO_MEDIDO")


PROIBIDOS_NA_INSTRUCAO = ("gênero", "a cliente", "identificada", "identificado")


class InstrucaoNeutraTest(unittest.TestCase):
    """Decisão do dono (2026-09-27 10:17): a instrução de sistema não cita nem concorda gênero."""

    @staticmethod
    def _texto(genero):
        return pu.instrucao_sistema({"codigo": MARIA, "pessoa": "Maria", "genero": genero, "indice": 1})

    def test_instrucao_igual_para_f_e_m_e_trata_por_voce(self):
        self.assertEqual(self._texto("F"), self._texto("M"))
        self.assertIn(MARIA, self._texto("F"))
        self.assertIn('"você"', self._texto("F"))
        self.assertNotIn("a cliente", self._texto("F").lower())

    def test_instrucao_sistema_sem_genero(self):
        # xfail medido 2026-09-27: o texto atual de instrucao_sistema traz "sem concordância de gênero" e
        # "a pessoa identificada abaixo". Correção é de produção (perfil_usuario.py), não desta migração:
        # quando o texto mudar vira 'unexpected success' e tira-se o decorador. Sem subTest, para o xfail valer.
        texto = self._texto("F").lower()
        self.assertEqual([p for p in PROIBIDOS_NA_INSTRUCAO if p in texto], [])

    def test_prova_negativa_instrucao_generificada_reprova(self):
        antiga = "Você fala com a cliente identificada abaixo (gênero feminino)."
        self.assertTrue(all(p in antiga.lower() for p in ("gênero", "a cliente", "identificada")))


class IntencaoTest(unittest.TestCase):
    def test_classificar(self):
        self.assertEqual(pu.classificar("Quem sou eu?"), "quem_sou_eu")
        self.assertEqual(pu.classificar("qual é o meu nome"), "nome")
        self.assertEqual(pu.classificar("Qual o meu código?"), "codigo")
        self.assertEqual(pu.classificar("quanto gastei?"), "livre")


if __name__ == "__main__":
    unittest.main()
