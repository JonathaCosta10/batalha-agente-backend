"""Contrato e consultas BigQuery do sorteio IAI. O cliente é injetável para testes."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

ARQUIVO_CONTRATO = Path(__file__).resolve().parents[1] / "contrato-de-extracao-e-resposta.json"


class Recusa(ValueError):
    """A extração ou a resposta não pode ser publicada."""


def contrato() -> dict:
    return json.loads(ARQUIVO_CONTRATO.read_text(encoding="utf-8"))


def serializar(valor):
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, dict):
        return {chave: serializar(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [serializar(item) for item in valor]
    return valor


def hash_json(dados) -> str:
    texto = json.dumps(dados, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def gravar_json(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(caminho.name + ".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporario.replace(caminho)


def validar_uuid(valor: str) -> None:
    if type(valor) is not str:
        raise Recusa("id_usuario não é texto UUID")
    try:
        if str(UUID(valor)) != valor:
            raise ValueError("forma não canônica")
    except ValueError as exc:
        raise Recusa("id_usuario não é UUID canônico") from exc


def validar_linha(linha: dict, regras: dict) -> dict:
    obrigatorios = regras["extracao"]["campos_obrigatorios_da_linha"]
    if type(linha) is not dict or set(linha) != set(obrigatorios):
        raise Recusa("estrutura da linha BigQuery diverge do contrato")
    if type(linha["anomesdia"]) is not str or not linha["anomesdia"]:
        raise Recusa("timestamp ausente")
    try:
        datetime.fromisoformat(linha["anomesdia"])
    except ValueError as exc:
        raise Recusa("timestamp inválido") from exc
    if type(linha["anomes"]) is not int or type(linha["vlr"]) not in (int, float, str):
        raise Recusa("tipo numérico inesperado no extrato")
    if type(linha["vlr"]) is str:
        try:
            if not Decimal(linha["vlr"]).is_finite():
                raise ValueError("não finito")
        except Exception as exc:
            raise Recusa("valor monetário inválido") from exc
    if type(linha["vlr"]) is float and not math.isfinite(linha["vlr"]):
        raise Recusa("valor monetário não finito")
    if linha["tipo"] not in regras["extracao"]["tipos_movimento"]:
        raise Recusa("tipo de movimento fora do contrato")
    if type(linha["nom_cate_macro"]) is not str or not linha["nom_cate_macro"]:
        raise Recusa("categoria ausente")
    return linha


class ConsultorBigQuery:
    def __init__(self, regras: dict):
        self.regras = regras
        self.jobs = []
        from google.cloud import bigquery
        self.bigquery = bigquery
        self.cliente = bigquery.Client(project=regras["fonte"]["projeto"])

    def executar(self, sql: str, parametros: list) -> list[dict]:
        bq = self.bigquery
        limite = self.regras["fonte"]["limite_bytes_por_consulta"]
        config = bq.QueryJobConfig(query_parameters=parametros, maximum_bytes_billed=limite, use_query_cache=False)
        seco = self.cliente.query(sql, job_config=bq.QueryJobConfig(query_parameters=parametros, dry_run=True, use_query_cache=False))
        if seco.total_bytes_processed > limite:
            raise Recusa(f"consulta estimada em {seco.total_bytes_processed} bytes, acima do limite")
        job = self.cliente.query(sql, job_config=config)
        linhas = [serializar(dict(linha)) for linha in job.result(timeout=60)]
        self.jobs.append({"job_id": job.job_id, "bytes_processados": job.total_bytes_processed, "linhas": len(linhas), "sql_sha256": hashlib.sha256(sql.encode("utf-8")).hexdigest()})
        return linhas

    def usuarios(self) -> list[str]:
        fonte = self.regras["fonte"]
        sql = (f"SELECT id_usuario FROM `{fonte['tabela']}` "
               "WHERE DATE(anomesdia, 'America/Sao_Paulo') <= @data_corte "
               "GROUP BY id_usuario ORDER BY id_usuario")
        parametros = [self.bigquery.ScalarQueryParameter("data_corte", "DATE", date.fromisoformat(fonte["data_corte"]))]
        return [linha["id_usuario"] for linha in self.executar(sql, parametros)]

    def movimentos(self, id_usuario: str) -> list[dict]:
        fonte = self.regras["fonte"]
        sql = ("SELECT anomesdia, anomes, tipo, vlr, nom_cate_macro "
               f"FROM `{fonte['tabela']}` WHERE id_usuario = @id_usuario "
               "AND DATE(anomesdia, 'America/Sao_Paulo') <= @data_corte "
               "ORDER BY anomesdia, anomes, tipo, vlr, nom_cate_macro")
        parametros = [
            self.bigquery.ScalarQueryParameter("id_usuario", "STRING", id_usuario),
            self.bigquery.ScalarQueryParameter("data_corte", "DATE", date.fromisoformat(fonte["data_corte"])),
        ]
        return [validar_linha(linha, self.regras) for linha in self.executar(sql, parametros)]
