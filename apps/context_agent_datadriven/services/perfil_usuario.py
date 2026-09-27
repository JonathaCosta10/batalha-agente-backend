"""
Perfil de usuário: "quem sou eu" para o agente.

A primeira chamada do front define o usuário (UUID ou índice do CSV da verdade) e recebe um
`sessao_id`. Daí em diante toda pergunta chega com esse `sessao_id`, e o agente sabe a quem
responde. A identidade vem de data/usuarios_verdade.csv (scripts/baixar_usuarios_verdade.py):
`codigo` = id_usuario da base, `pessoa` = nome inventado no CSV, `genero` = F/M inventado.

O Gemini redige a resposta só com esses fatos. O guard confere, na resposta, a presença do nome e
do código que a pergunta pediu; resposta que não os traz não sai como sucesso.
"""

import csv
import json
import re
import threading
import time
import unicodedata
import uuid
from pathlib import Path

from django.conf import settings

from desafio_itau.modelos_llm import MODELOS_GOOGLE
from ..agentes.LLM_Models.google.cliente import GoogleLLMCliente

ARQUIVO_CSV = Path(settings.BASE_DIR) / "data" / "usuarios_verdade.csv"
SESSAO_SEGUNDOS = 4 * 60 * 60
PADRAO_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class BaseAusente(RuntimeError):
    """O CSV da verdade não foi baixado."""


class ReferenciaInvalida(ValueError):
    """A referência não é índice inteiro nem UUID."""


class UsuarioNaoEncontrado(LookupError):
    """Índice fora de 1..N ou UUID que não está no CSV."""


class SessaoNaoEncontrada(LookupError):
    """sessao_id desconhecido ou expirado: o front chama definir de novo."""


class ModeloIndisponivel(RuntimeError):
    """Nenhum modelo respondeu."""


class RespostaReprovada(RuntimeError):
    """O modelo respondeu sem o nome/código que a pergunta pediu."""

    def __init__(self, faltam, resposta, modelo):
        super().__init__(f"A resposta do modelo não trouxe: {', '.join(faltam)}.")
        self.faltam, self.resposta, self.modelo = faltam, resposta, modelo


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------- base da verdade

_base = {"mtime": None, "por_indice": {}, "por_uuid": {}}
_trava_base = threading.Lock()


def _carregar() -> dict:
    if not ARQUIVO_CSV.exists():
        raise BaseAusente("CSV da verdade ausente: rode scripts/baixar_usuarios_verdade.py.")
    mtime = ARQUIVO_CSV.stat().st_mtime
    with _trava_base:
        if _base["mtime"] != mtime:
            with ARQUIVO_CSV.open(encoding="utf-8", newline="") as entrada:
                linhas = list(csv.DictReader(entrada))
            _base["por_indice"] = {int(l["indice"]): l for l in linhas}
            _base["por_uuid"] = {l["id_usuario"]: l for l in linhas}
            _base["mtime"] = mtime
        return _base


def identificar(referencia) -> dict:
    """Índice ('1') ou UUID -> {codigo, pessoa, genero, indice}."""
    ref = str(referencia if referencia is not None else "").strip().lower()
    base = _carregar()
    # P0 do dono (2026-09-27 10:32, via f7): a identidade sai só do id_usuario; o índice posicional do CSV
    # não identifica ninguém (a posição muda se a base mudar) e deixa de ser aceito.
    if re.fullmatch(r"[0-9]+", ref):
        raise ReferenciaInvalida("Índice posicional descontinuado: envie usuario com o id_usuario (UUID).")
    if PADRAO_UUID.fullmatch(ref):
        linha = base["por_uuid"].get(ref)
        if not linha:
            raise UsuarioNaoEncontrado(f"id_usuario {ref} não está no CSV da verdade.")
    else:
        raise ReferenciaInvalida("Envie usuario com o id_usuario (UUID).")
    return {"codigo": linha["id_usuario"], "pessoa": linha["nome"], "genero": linha["genero"],
            "indice": int(linha["indice"])}


# ---------------------------------------------------------------- sessões

# Decisão D-4, 2026-09-27: as sessões ficam no SQLite (model SessaoPerfilUsuario), não num dict do processo,
# para sobreviverem ao reinício do runserver. Mesma interface pública (definir_usuario / usuario_da_sessao /
# SessaoNaoEncontrada) e mesmo TTL (SESSAO_SEGUNDOS, 4 h). O relógio passa a ser de parede (época Unix),
# porque time.monotonic() não tem sentido entre dois processos; os testes trocam `_relogio`.
_relogio = time.time


class _ArmazemSessoes:
    """Sessões no banco com a forma de dict usada antes: [sid] = {...}, get, pop, clear. Sem estado em memória."""

    @staticmethod
    def _model():
        from ..models import SessaoPerfilUsuario
        return SessaoPerfilUsuario

    def __setitem__(self, sessao_id, sessao):
        self._model().objects.update_or_create(
            sessao_id=str(sessao_id),
            defaults={"usuario_json": json.dumps(sessao["usuario"], ensure_ascii=False), "criada_em": sessao["criada"]},
        )

    def get(self, sessao_id, padrao=None):
        linha = self._model().objects.filter(sessao_id=str(sessao_id)).first()
        if linha is None:
            return padrao
        return {"usuario": json.loads(linha.usuario_json), "criada": linha.criada_em}

    def pop(self, sessao_id, padrao=None):
        sessao = self.get(sessao_id, padrao)
        self._model().objects.filter(sessao_id=str(sessao_id)).delete()
        return sessao

    def clear(self):
        self._model().objects.all().delete()

    def expurgar(self, agora):
        """Apaga as vencidas (chamado a cada definir; mantém a tabela pequena)."""
        self._model().objects.filter(criada_em__lt=agora - SESSAO_SEGUNDOS).delete()


_sessoes = _ArmazemSessoes()
_trava_sessoes = threading.Lock()


def definir_usuario(referencia) -> dict:
    usuario = identificar(referencia)
    sessao_id = uuid.uuid4().hex
    agora = _relogio()
    with _trava_sessoes:
        _sessoes.expurgar(agora)
        _sessoes[sessao_id] = {"usuario": usuario, "criada": agora}
    # O 201 só mostra o que o cliente pode ver: código e nome gerado (selo em nome_origem). Gênero e índice
    # ficam na sessão para uso interno e não saem (dono 10:17: padrão neutro).
    publico = {"codigo": usuario["codigo"], "pessoa": usuario["pessoa"], "nome_origem": "nome_gerado"}
    return {"sessao_id": sessao_id, "usuario": publico, "expira_em_segundos": SESSAO_SEGUNDOS}


def usuario_da_sessao(sessao_id) -> dict:
    sessao_id = str(sessao_id or "")
    with _trava_sessoes:
        sessao = _sessoes.get(sessao_id) if sessao_id else None
        if sessao and _relogio() - sessao["criada"] > SESSAO_SEGUNDOS:
            _sessoes.pop(sessao_id, None)
            sessao = None
    if not sessao:
        raise SessaoNaoEncontrada("sessao_id desconhecido ou expirado: chame perfil-usuario/definir/ de novo.")
    return sessao["usuario"]


# ---------------------------------------------------------------- pergunta

INTENCOES = {
    "quem_sou_eu": re.compile(r"quem (e que )?sou eu|me identifi|quem esta falando|sabe quem eu sou"),
    "nome": re.compile(r"(meu|qual (e )?o meu) nome|como (eu )?me chamo"),
    "codigo": re.compile(r"(meu|qual (e )?o meu) (codigo|id|identificador)"),
}
EXIGE = {"quem_sou_eu": ("pessoa", "codigo"), "nome": ("pessoa",), "codigo": ("codigo",)}


def classificar(pergunta: str) -> str:
    texto = _sem_acento(pergunta)
    for intencao, padrao in INTENCOES.items():
        if padrao.search(texto):
            return intencao
    return "livre"


def instrucao_sistema(usuario: dict) -> str:
    # Neutro por decisão do dono (10:17): gênero não entra no prompt; trate a pessoa por "você".
    return (
        "Você é o assistente financeiro da Organizesee, conversando em português do Brasil.\n"
        "Você conversa com a pessoa descrita abaixo; trate-a sempre por \"você\" e use só formas neutras. "
        "Estes são os únicos fatos verificados sobre essa pessoa:\n"
        f"- pessoa (primeiro nome gerado para o código): {usuario['pessoa']}\n"
        f"- código (id_usuario na base): {usuario['codigo']}\n"
        "Regras:\n"
        "1. Se perguntarem quem é a pessoa, responda com o nome e o código exatamente como acima.\n"
        "2. Escreva o código completo, sem abreviar nem formatar.\n"
        "3. Não invente sobrenome, idade, saldo, renda nem qualquer outro dado; se pedirem algo "
        "que não está acima, diga que ainda não tem essa informação.\n"
        "4. Seja breve e cordial: no máximo três frases."
    )


def conferir(resposta: str, usuario: dict, intencao: str) -> list:
    """Guard: devolve o que a intenção exige e a resposta não traz."""
    texto = _sem_acento(resposta)
    presentes = {
        "pessoa": _sem_acento(usuario["pessoa"]) in texto,
        "codigo": usuario["codigo"].lower() in resposta.lower(),
    }
    return [campo for campo in EXIGE.get(intencao, ()) if not presentes[campo]]


def perguntar(sessao_id, pergunta: str, cliente=GoogleLLMCliente, modelos=None) -> dict:
    usuario = usuario_da_sessao(sessao_id)
    intencao = classificar(pergunta)
    sistema = instrucao_sistema(usuario)
    conteudo = [{"role": "user", "parts": [{"text": pergunta}]}]
    erros, reprovada = [], None
    for modelo in modelos or MODELOS_GOOGLE:
        resultado = cliente.executar_chamada(modelo, sistema, conteudo, temperatura=0.2, max_tokens=300)
        if not resultado.get("sucesso"):
            erros.append(f"{modelo}: {resultado.get('erro')}")
            continue
        faltam = conferir(resultado["resposta"], usuario, intencao)
        if faltam:
            reprovada = RespostaReprovada(faltam, resultado["resposta"], modelo)
            continue
        return {
            "sessao_id": sessao_id,
            "usuario": {"codigo": usuario["codigo"], "pessoa": usuario["pessoa"], "nome_origem": "nome_gerado"},
            "pergunta": pergunta,
            "intencao": intencao,
            "resposta": resultado["resposta"],
            "modelo": modelo,
            "origem_resposta": "modelo",
            "guard": {"estado": "APROVADO", "conferido": list(EXIGE.get(intencao, ()))},
        }
    if reprovada:
        raise reprovada
    raise ModeloIndisponivel("Nenhum modelo respondeu. " + " | ".join(erros))
