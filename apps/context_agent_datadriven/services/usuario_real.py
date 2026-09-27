"""
Usuário real: os id_usuario (UUID) do extrato no BigQuery, lidos com ADC, com as visões do estudo i.agora.

A referência de um usuário é o UUID da base ou o índice 1..N da lista ordenada por id_usuario
(ROW_NUMBER() OVER (ORDER BY id_usuario)). O índice é estável enquanto a tabela não mudar;
não é o `cliente_id` sintético das rotas /api/v1/cliente/ (lá 928 é "Eduarda Soares",
aqui 928 é o 928.º UUID) — a base real não tem nome nem gênero.

Toda resposta leva um selo: fonte, hora BRT da medição, job_id e bytes de cada consulta.
Resultado de cache devolve o selo da medição original com `cache: true`.
"""

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.conf import settings

from ..pastas_raiz.estudos.i_agora import t3, visoes

BRT = ZoneInfo("America/Sao_Paulo")
TOPICOS_PERFIL = ("perfil_t3", "renda", "dividas", "recorrencias", "discricionario")
PADRAO_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

SQL_LISTA = """
SELECT
  ROW_NUMBER() OVER (ORDER BY id_usuario) AS indice,
  id_usuario,
  COUNT(*) AS movimentos,
  COUNT(DISTINCT anomes) AS meses,
  MIN(anomes) AS primeiro_anomes,
  MAX(anomes) AS ultimo_anomes
FROM `{tabela}`
GROUP BY id_usuario
ORDER BY id_usuario
"""


class UsuarioRealDesligado(RuntimeError):
    """USUARIO_REAL['ATIVO'] é False: nenhuma consulta sai."""


class ReferenciaInvalida(ValueError):
    """A referência não é índice inteiro nem UUID."""


class UsuarioNaoEncontrado(LookupError):
    """Índice fora de 1..N ou UUID que não existe na tabela."""


class FonteIndisponivel(RuntimeError):
    """BigQuery não respondeu (sem ADC, sem rede, sem permissão, dry-run acima do limite)."""


def configuracao() -> dict:
    return settings.USUARIO_REAL


def _agora_brt() -> str:
    return datetime.now(BRT).isoformat(timespec="seconds")


class _Cache:
    """Cache em memória do processo, com validade em segundos."""

    def __init__(self):
        self._dados = {}
        self._trava = threading.Lock()

    def obter(self, chave):
        with self._trava:
            item = self._dados.get(chave)
        if item and time.monotonic() - item[0] < configuracao()["CACHE_SEGUNDOS"]:
            return item[1]
        return None

    def guardar(self, chave, valor):
        with self._trava:
            self._dados[chave] = (time.monotonic(), valor)

    def limpar(self):
        with self._trava:
            self._dados.clear()


cache = _Cache()
_cliente_bq = None
_trava_cliente = threading.Lock()


def _cliente():
    global _cliente_bq
    with _trava_cliente:
        if _cliente_bq is None:
            from google.cloud import bigquery
            _cliente_bq = bigquery.Client(project=configuracao()["PROJETO"])
        return _cliente_bq


def _novo_executor():
    """Um executor por consulta, para cada uma guardar o seu job_id. Os testes trocam esta função."""
    return visoes.ExecutorBigQuery(cliente=_cliente())


def _exigir_ativo():
    if not configuracao()["ATIVO"]:
        raise UsuarioRealDesligado("Fonte usuário real desligada (USUARIO_REAL_ATIVO=0).")


def _selo(jobs: dict, bytes_total: int, tempo_ms: float) -> dict:
    return {
        "fonte": configuracao()["TABELA"],
        "natureza_da_base": "sintetica",
        "autenticacao": "ADC",
        "medido_em": _agora_brt(),
        "jobs": jobs,
        "bytes_processados": bytes_total,
        "tempo_consulta_ms": round(tempo_ms, 1),
        "cache": False,
    }


def listar_usuarios() -> dict:
    """Todos os usuários da tabela, com índice estável. Uma consulta, guardada em cache."""
    _exigir_ativo()
    em_cache = cache.obter("lista")
    if em_cache:
        return {**em_cache, "selo": {**em_cache["selo"], "cache": True}}
    executor = _novo_executor()
    inicio = time.perf_counter()
    try:
        linhas = executor.executar(SQL_LISTA.format(tabela=configuracao()["TABELA"]), {})
    except Exception as erro:  # google.api_core, auth, rede: todos viram 503 com a causa
        raise FonteIndisponivel(f"{type(erro).__name__}: {erro}") from erro
    job = getattr(executor, "ultimo_job", {}) or {}
    resultado = {
        "usuarios": linhas,
        "total": len(linhas),
        "selo": _selo({"lista": job.get("job_id")}, job.get("bytes_processados", 0),
                      (time.perf_counter() - inicio) * 1000),
    }
    cache.guardar("lista", resultado)
    return resultado


def resolver(referencia: str) -> dict:
    """Índice ('928') ou UUID -> a linha da lista {indice, id_usuario, movimentos, meses, ...}."""
    ref = str(referencia).strip().lower()
    usuarios = listar_usuarios()["usuarios"]
    if re.fullmatch(r"[0-9]+", ref):
        indice = int(ref)
        if not 1 <= indice <= len(usuarios):
            raise UsuarioNaoEncontrado(f"Índice {indice} fora de 1..{len(usuarios)}.")
        return usuarios[indice - 1]
    if PADRAO_UUID.fullmatch(ref):
        for usuario in usuarios:
            if usuario["id_usuario"] == ref:
                return usuario
        raise UsuarioNaoEncontrado(f"id_usuario {ref} não existe em {configuracao()['TABELA']}.")
    raise ReferenciaInvalida("Use o índice (1..N) ou o id_usuario (UUID) da base.")


def validar_data_corte(texto) -> date:
    if texto in (None, ""):
        return date.fromisoformat(configuracao()["DATA_CORTE"])
    try:
        return date.fromisoformat(str(texto))
    except ValueError as erro:
        raise ReferenciaInvalida("data_corte deve ser AAAA-MM-DD.") from erro


def _consultar(topico, id_usuario, data_corte, categoria=None):
    executor = _novo_executor()
    try:
        visao = visoes.consultar_visao(topico, id_usuario, data_corte, categoria=categoria, executor=executor)
    except visoes.ForaDoCatalogo:
        raise
    except Exception as erro:
        raise FonteIndisponivel(f"{topico}: {type(erro).__name__}: {erro}") from erro
    return visao, getattr(executor, "ultimo_job", {}) or {}


def consultar_topicos(usuario: dict, topicos, data_corte: date, categoria=None) -> tuple[dict, dict]:
    """Roda as visões em paralelo. Devolve ({topico: visao}, selo)."""
    inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(topicos)) as pool:
        futuros = {t: pool.submit(_consultar, t, usuario["id_usuario"], data_corte, categoria) for t in topicos}
        resultados = {t: f.result() for t, f in futuros.items()}
    visoes_por_topico = {t: v for t, (v, _) in resultados.items()}
    jobs = {t: j.get("job_id") for t, (_, j) in resultados.items()}
    bytes_total = sum(j.get("bytes_processados", 0) for _, j in resultados.values())
    return visoes_por_topico, _selo(jobs, bytes_total, (time.perf_counter() - inicio) * 1000)


def _resumo(perfil_t3: dict) -> dict:
    linha = perfil_t3["linha"]
    segmento = linha.get("segmento_t3")
    tese = t3.PERFIS_DE_RESPOSTA.get(segmento, {})
    return {
        "segmento_t3": segmento,
        "inflow_mensal": linha.get("inflow_mensal"),
        "outflow_mensal": linha.get("outflow_mensal"),
        "surplus_mensal": linha.get("surplus_mensal"),
        "taxa_surplus_pct": linha.get("taxa_surplus_pct"),
        "meses_na_janela": linha.get("meses"),
        "saidas_sem_grupo": linha.get("saidas_sem_grupo"),
        "perfil_de_resposta": {"tom": tese.get("tom"), "foco": tese.get("foco")} if tese else None,
    }


def perfil(referencia: str, data_corte=None) -> dict:
    """Usuário + as cinco visões + resumo T3. Guardado em cache por (UUID, data de corte)."""
    usuario = resolver(referencia)
    corte = validar_data_corte(data_corte)
    chave = ("perfil", usuario["id_usuario"], corte.isoformat())
    em_cache = cache.obter(chave)
    if em_cache:
        return {**em_cache, "selo": {**em_cache["selo"], "cache": True}}
    por_topico, selo = consultar_topicos(usuario, TOPICOS_PERFIL, corte)
    resultado = {
        "usuario": usuario,
        "data_corte": corte.isoformat(),
        "janela": "meses completos antes do mês da data de corte",
        "resumo": _resumo(por_topico["perfil_t3"]),
        "visoes": {t: por_topico[t]["linha"] for t in TOPICOS_PERFIL},
        "sql_sha256": {t: por_topico[t]["sql_sha256"] for t in TOPICOS_PERFIL},
        "selo": selo,
    }
    cache.guardar(chave, resultado)
    return resultado


def visao(referencia: str, topico: str, categoria=None, data_corte=None) -> dict:
    """Uma visão do catálogo (visoes.TOPICOS). Tópico ou categoria fora do catálogo: ForaDoCatalogo."""
    if topico not in visoes.TOPICOS:
        raise visoes.ForaDoCatalogo(f"Tópico fora do catálogo: {topico!r}. Válidos: {sorted(visoes.TOPICOS)}.")
    usuario = resolver(referencia)
    corte = validar_data_corte(data_corte)
    por_topico, selo = consultar_topicos(usuario, (topico,), corte, categoria)
    resultado = por_topico[topico]
    return {"usuario": usuario, "data_corte": corte.isoformat(), "topico": topico,
            "parametros": resultado["parametros"], "linha": resultado["linha"],
            "sql_sha256": resultado["sql_sha256"], "selo": selo}


def responder_pergunta(referencia: str, pergunta: str, data_corte=None) -> dict:
    """Roteia a pergunta para UMA visão (sem LLM) e devolve os números que a fundamentam."""
    topico, categoria = visoes.rotear(pergunta)
    resposta = visao(referencia, topico, categoria=categoria, data_corte=data_corte)
    return {"pergunta": pergunta, "categoria": categoria, **resposta}


# Saldo do mês da linha de corte (dia 1 até a data de corte, inclusive): o "Dezembro/25" da home.
SQL_SALDO_MES = """
SELECT
  COUNT(*) AS lancamentos,
  ROUND(IFNULL(SUM(IF(tipo = 'E', ABS(vlr), 0)), 0), 2) AS entradas,
  ROUND(IFNULL(SUM(IF(tipo = 'S', ABS(vlr), 0)), 0), 2) AS saidas
FROM `batalha-time-02-lxof.hackathon_dados.extrato_sintetico`
WHERE id_usuario = @id_usuario
  AND DATE(anomesdia) BETWEEN DATE_TRUNC(@data_corte, MONTH) AND @data_corte
"""


def montar_saldo_mes(linha: dict, corte: date, resumo: dict) -> dict:
    """Parte pura. `negativado` segue o saldo do mês até o corte (o número que a home mostra)."""
    entradas, saidas = float(linha["entradas"] or 0), float(linha["saidas"] or 0)
    saldo = round(entradas - saidas, 2)
    surplus = resumo.get("surplus_mensal")
    return {
        "periodo": {"de": corte.replace(day=1).isoformat(), "ate": corte.isoformat(),
                    "rotulo": f"até {corte.strftime('%d/%m/%Y')}"},
        "entradas": entradas,
        "saidas": saidas,
        "saldo": saldo,
        "lancamentos": int(linha["lancamentos"] or 0),
        "negativado": saldo < 0,
        "media_mensal": {k: resumo.get(k) for k in ("inflow_mensal", "outflow_mensal", "surplus_mensal", "meses_na_janela")},
        "negativado_na_media": "NAO_MEDIDO" if surplus is None else float(surplus) < 0,
    }


def saldo_mes(referencia: str, data_corte=None) -> dict:
    """Entradas, saídas e saldo do mês da linha de corte, com selo, e a média da janela ao lado."""
    usuario = resolver(referencia)
    corte = validar_data_corte(data_corte)
    chave = ("saldo_mes", usuario["id_usuario"], corte.isoformat())
    em_cache = cache.obter(chave)
    if em_cache:
        return {**em_cache, "selo": {**em_cache["selo"], "cache": True}}
    resumo = perfil(referencia, data_corte=data_corte)["resumo"]
    executor = _novo_executor()
    inicio = time.perf_counter()
    try:
        [linha] = executor.executar(SQL_SALDO_MES, {"id_usuario": usuario["id_usuario"], "data_corte": corte})
    except Exception as erro:
        raise FonteIndisponivel(f"saldo_mes: {type(erro).__name__}: {erro}") from erro
    job = getattr(executor, "ultimo_job", {}) or {}
    resultado = {"usuario": usuario, "data_corte": corte.isoformat(), **montar_saldo_mes(linha, corte, resumo),
                 "selo": _selo({"saldo_mes": job.get("job_id")}, job.get("bytes_processados", 0),
                               (time.perf_counter() - inicio) * 1000)}
    cache.guardar(chave, resultado)
    return resultado


def estado(validar: bool = False) -> dict:
    """ON/OFF e, com validar=True, uma consulta real (a lista, que fica em cache)."""
    cfg = configuracao()
    corpo = {
        "fonte": "usuario_real",
        "estado": "ON" if cfg["ATIVO"] else "OFF",
        "projeto": cfg["PROJETO"],
        "tabela": cfg["TABELA"],
        "data_corte_padrao": cfg["DATA_CORTE"],
        "cache_segundos": cfg["CACHE_SEGUNDOS"],
        "topicos": {t: c["descricao"] for t, c in visoes.TOPICOS.items()},
        "categorias": sorted(t3.MAPA_GRUPOS),
        "conexao": "NAO_MEDIDO",
    }
    if cfg["ATIVO"] and validar:
        try:
            lista = listar_usuarios()
            corpo.update(conexao="VALIDADA", total_usuarios=lista["total"], selo=lista["selo"])
        except FonteIndisponivel as erro:
            corpo.update(conexao="FALHOU", erro=str(erro))
    return corpo
