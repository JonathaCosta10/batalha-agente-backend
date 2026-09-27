"""
Visões por assunto sobre UM cliente, no corte da tese.

Cada tópico é um SQL parametrizado (sql/visao_*.sql, precedido de sql/_base_cliente.sql)
que devolve UMA linha. O agente recebe essa linha para responder; o guard
(guard.py) reexecuta o MESMO SQL com os MESMOS parâmetros e compara.

    rotear(pergunta)                        -> (tópico, categoria | None)
    montar_sql(tópico)                      -> SQL final (mapa de grupos e limiar injetados)
    consultar_visao(tópico, cliente, corte) -> {"topico", "parametros", "sql_sha256", "linha"}

Tópico ou categoria fora do catálogo é erro: o agente não responde sem visão.
"""

import hashlib
import re
import unicodedata
from datetime import date
from decimal import Decimal
from pathlib import Path

from . import t3

PASTA_SQL = Path(__file__).resolve().parent / "sql"
DATA_CORTE_TESE = date(2025, 12, 22)
LIMITE_BYTES = 100 * 1024 * 1024  # dry-run acima disto não roda

TOPICOS = {
    "perfil_t3": {
        "arquivo": "visao_perfil_t3.sql",
        "descricao": "Inflow, Outflow, Surplus mensais, grupos de saída e segmento T3.",
        "palavras": ("sobra", "sobrar", "saldo", "perfil", "situacao", "surplus",
                     "fluxo", "como estou", "segmento", "folga"),
    },
    "categoria": {
        "arquivo": "visao_categoria.sql",
        "descricao": "Gasto numa macro de saída: total, média mensal e % do Outflow.",
        "palavras": (),  # escolhido quando a pergunta cita uma macro de t3.MAPA_GRUPOS
        "parametros": ("categoria",),
    },
    "renda": {
        "arquivo": "visao_renda.sql",
        "descricao": "Fontes de entrada (CLT, diversos, outras) e volatilidade do Inflow.",
        "palavras": ("renda", "salario", "ganho", "recebo", "receita", "entrada", "clt", "autonomo",
                     "volatil", "instavel"),
    },
    "dividas": {
        "arquivo": "visao_dividas.sql",
        "descricao": "Compromisso financeiro: empréstimos, fatura, juros, multas e % do Inflow.",
        "palavras": ("divida", "emprestimo", "financiamento", "juros", "fatura", "parcela", "multa",
                     "devendo", "negativ", "cartao"),
    },
    "recorrencias": {
        "arquivo": "visao_recorrencias.sql",
        "descricao": "Assinaturas: lançamentos, total, média mensal e serviços distintos.",
        "palavras": ("assinatura", "recorrente", "recorrencia", "mensalidade", "streaming"),
    },
    "discricionario": {
        "arquivo": "visao_discricionario.sql",
        "descricao": "Maior categoria discricionária e média mensal do grupo.",
        "palavras": ("cortar", "economizar", "economia", "reduzir", "superfluo", "gastando demais",
                     "onde gasto", "lazer"),
    },
}


class ForaDoCatalogo(ValueError):
    """Tópico, categoria ou pergunta sem visão: o agente não deve responder com número."""


def normalizar_texto(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acento.casefold().split())


_CATEGORIAS_NORMALIZADAS = {normalizar_texto(m): m for m in t3.MAPA_GRUPOS}


def validar_categoria(categoria: str) -> str:
    """Devolve a grafia da base; categoria fora de t3.MAPA_GRUPOS é erro."""
    oficial = _CATEGORIAS_NORMALIZADAS.get(normalizar_texto(categoria or ""))
    if oficial is None:
        raise ForaDoCatalogo(f"Categoria fora do mapa T3: {categoria!r}.")
    return oficial


def rotear(pergunta: str) -> tuple[str, str | None]:
    """Pergunta -> tópico. Macro citada pelo nome vence; depois a contagem de palavras-chave."""
    texto = " ".join(re.sub(r"[^a-z0-9]", " ", normalizar_texto(pergunta)).split())
    citadas = [oficial for norm, oficial in _CATEGORIAS_NORMALIZADAS.items() if f" {norm} " in f" {texto} "]
    if citadas:
        return "categoria", max(citadas, key=len)
    pontos = {t: sum(p in texto for p in cfg["palavras"]) for t, cfg in TOPICOS.items()}
    melhor = max(pontos, key=lambda t: pontos[t])
    if pontos[melhor] == 0:
        raise ForaDoCatalogo(f"Pergunta sem tópico no catálogo: {pergunta!r}.")
    return melhor, None


def montar_sql(topico: str) -> str:
    if topico not in TOPICOS:
        raise ForaDoCatalogo(f"Tópico fora do catálogo: {topico!r}.")
    base = (PASTA_SQL / "_base_cliente.sql").read_text(encoding="utf-8")
    visao = (PASTA_SQL / TOPICOS[topico]["arquivo"]).read_text(encoding="utf-8")
    return t3.renderizar_sql(base + visao)


def _parametros(id_usuario: str, data_corte: date, categoria: str | None, topico: str) -> dict:
    parametros = {"id_usuario": id_usuario, "data_corte": data_corte}
    if "categoria" in TOPICOS[topico].get("parametros", ()):
        parametros["categoria"] = validar_categoria(categoria)
    elif categoria is not None:
        raise ForaDoCatalogo(f"Tópico {topico!r} não recebe categoria.")
    return parametros


def _valor_json(valor):
    return float(valor) if isinstance(valor, Decimal) else valor


class ExecutorBigQuery:
    """Roda o SQL no BigQuery via ADC. Dry-run primeiro: acima de `limite_bytes` não roda."""

    def __init__(self, cliente=None, limite_bytes: int = LIMITE_BYTES):
        self._cliente = cliente
        self.limite_bytes = limite_bytes

    @property
    def cliente(self):
        if self._cliente is None:
            from google.cloud import bigquery
            self._cliente = bigquery.Client(project="batalha-time-02-lxof")
        return self._cliente

    def executar(self, sql: str, parametros: dict) -> list[dict]:
        from google.cloud import bigquery
        tipos = {str: "STRING", date: "DATE", float: "FLOAT64", int: "INT64"}
        config = dict(query_parameters=[
            bigquery.ScalarQueryParameter(nome, tipos[type(valor)], valor) for nome, valor in parametros.items()
        ])
        seco = self.cliente.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False, **config))
        if seco.total_bytes_processed > self.limite_bytes:
            raise RuntimeError(f"Dry-run {seco.total_bytes_processed} bytes > limite {self.limite_bytes}.")
        job = self.cliente.query(sql, job_config=bigquery.QueryJobConfig(**config))
        self.ultimo_job = {"job_id": job.job_id, "bytes_processados": seco.total_bytes_processed}
        return [dict(linha) for linha in job.result()]


def consultar_visao(topico: str, id_usuario: str, data_corte: date = DATA_CORTE_TESE,
                    categoria: str | None = None, executor=None) -> dict:
    """Uma visão, uma linha. `executor` precisa de .executar(sql, parametros) -> list[dict]."""
    sql = montar_sql(topico)
    parametros = _parametros(id_usuario, data_corte, categoria, topico)
    linhas = (executor or ExecutorBigQuery()).executar(sql, parametros)
    if len(linhas) != 1:
        raise RuntimeError(f"Visão {topico} devolveu {len(linhas)} linhas; o contrato é 1.")
    return {
        "topico": topico,
        "parametros": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in parametros.items()},
        "sql_sha256": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
        "linha": {k: _valor_json(v) for k, v in linhas[0].items()},
    }
