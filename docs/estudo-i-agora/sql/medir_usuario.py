"""Mede a pergunta dirigida sobre um usuário, sem enviar dados a um LLM.

Uso: python docs/estudo-i-agora/sql/medir_usuario.py 1 --saida caminho.json
Requer Application Default Credentials com acesso de leitura à tabela BigQuery.
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

from google.cloud import bigquery


PROJETO = "batalha-time-02-lxof"
FONTE = f"{PROJETO}.hackathon_dados.extrato_sintetico"
SQL = Path(__file__).with_name("q07_fluxo_usuario.sql")
LIMITE_BYTES = 100_000_000
BRT = timezone(timedelta(hours=-3))


def serializar(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, (list, tuple)):
        return [serializar(item) for item in valor]
    if hasattr(valor, "items"):
        return {chave: serializar(item) for chave, item in valor.items()}
    return valor


def checar_fatos(fatos, corte):
    """Checagens mecânicas; não se apresentam como avaliação semântica de LLM."""
    checks = {
        "tipos_e_s": fatos["total_movimentos"] == fatos["movimentos_entrada"] + fatos["movimentos_saida"],
        "soma_mensal_movimentos": fatos["total_movimentos"] == sum(m["movimentos"] for m in fatos["meses"]),
        "soma_mensal_entradas": abs(fatos["entradas_total"] - sum(m["entradas"] for m in fatos["meses"])) <= 0.05,
        "soma_mensal_saidas": abs(fatos["saidas_total"] - sum(m["saidas"] for m in fatos["meses"])) <= 0.05,
        "saldo_consistente": abs(fatos["saldo_periodo"] - (fatos["entradas_total"] - fatos["saidas_total"])) <= 0.05,
        "respeita_corte": (fatos["ultima_movimentacao"] is None or
                           datetime.fromisoformat(fatos["ultima_movimentacao"]).astimezone(BRT).date() <= corte),
    }
    return checks


def medir(id_usuario, corte):
    inicio = perf_counter()
    cliente = bigquery.Client(project=PROJETO)
    parametros = [
        bigquery.ScalarQueryParameter("id_usuario", "STRING", id_usuario),
        bigquery.ScalarQueryParameter("data_corte", "DATE", corte),
    ]
    consulta = SQL.read_text(encoding="utf-8")
    estimativa = cliente.query(consulta, job_config=bigquery.QueryJobConfig(
        query_parameters=parametros, dry_run=True, use_query_cache=False,
    ))
    if estimativa.total_bytes_processed > LIMITE_BYTES:
        raise ValueError(f"NAO_MEDIDO: consulta estimada em {estimativa.total_bytes_processed} bytes, acima do limite.")

    inicio_query = perf_counter()
    job = cliente.query(consulta, job_config=bigquery.QueryJobConfig(
        query_parameters=parametros, maximum_bytes_billed=LIMITE_BYTES,
    ))
    linha = next(iter(job.result(timeout=60)))
    duracao_query_ms = round((perf_counter() - inicio_query) * 1000)
    fatos = serializar(dict(linha))
    checks = {} if fatos["total_movimentos"] == 0 else checar_fatos(fatos, corte)
    estado = "VAZIO" if fatos["total_movimentos"] == 0 else ("COMPROVADO" if all(checks.values()) else "REPROVADO")
    return {
        "pergunta": f"Como evoluiu o fluxo do usuário {id_usuario} até {corte.isoformat()}?",
        "id_usuario": id_usuario,
        "data_corte": corte.isoformat(),
        "estado": estado,
        "fonte_oficial": FONTE,
        "natureza_da_base": "sintetica",
        "data_base": fatos["ultima_movimentacao"],
        "ultima_atualizacao": datetime.now(BRT).isoformat(),
        "job_id": job.job_id,
        "bytes_processados": job.total_bytes_processed,
        "tempo_consulta_ms": duracao_query_ms,
        "tempo_total_ms": round((perf_counter() - inicio) * 1000),
        "controles_factuais": checks,
        "fatos": fatos,
        "avaliacao_semantica_llm": "NAO_MEDIDO",
        "motivo": "Nenhum movimento encontrado para este ID literal e período." if estado == "VAZIO" else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("id_usuario", help="ID exato; enviado como parâmetro BigQuery")
    parser.add_argument("--data-corte", type=date.fromisoformat, default=date(2025, 12, 22))
    parser.add_argument("--saida", type=Path)
    args = parser.parse_args()
    try:
        resultado = medir(args.id_usuario, args.data_corte)
    except Exception as erro:
        print(f"NAO_MEDIDO: {type(erro).__name__}: {erro}", file=sys.stderr)
        return 1
    texto = json.dumps(resultado, ensure_ascii=False, indent=2) + "\n"
    if args.saida:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(texto, encoding="utf-8")
        print(f"{resultado['estado']}: {resultado['tempo_total_ms']} ms -> {args.saida}")
    else:
        print(texto)
    return 0 if resultado["estado"] != "REPROVADO" else 2


if __name__ == "__main__":
    sys.exit(main())
