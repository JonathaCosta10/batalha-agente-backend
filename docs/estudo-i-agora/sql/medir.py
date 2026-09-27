"""Roda as consultas q*.sql na tabela real do BigQuery e grava cada resultado com selo.

Autenticação: Application Default Credentials (ADC). Chave de API é vedada pela
política da organização. Preparar o ADC uma vez por máquina:

    gcloud auth application-default login
    gcloud auth application-default set-quota-project batalha-time-02-lxof

Uso (da raiz do projeto Django):

    python docs/estudo-i-agora/sql/medir.py            # todas as consultas
    python docs/estudo-i-agora/sql/medir.py q03 q04    # só as indicadas

Saída: docs/estudo-i-agora/medicoes/<AAAA-MM-DD>/<consulta>.json, com consulta,
fonte, horário BRT, job_id, bytes processados e linhas. Se a consulta falhar,
nada é gravado e o erro é impresso: sem medição não há número.

Parâmetros: `{{GRUPOS}}`/`{{LIMIAR_SURPLUS}}` vêm de i_agora/t3.py; `@data_corte` recebe o
corte da tese (2025-12-22). Consulta com `@id_usuario` é por cliente e fica de fora
(ver medir_usuario.py e medir_t3.py).
"""

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora.t3 import renderizar_sql  # noqa: E402

PROJETO = "batalha-time-02-lxof"
TABELA = f"{PROJETO}.hackathon_dados.extrato_sintetico"
BRT = timezone(timedelta(hours=-3))
PASTA_SQL = Path(__file__).resolve().parent
DATA_CORTE = date(2025, 12, 22)


def medir(filtros: list[str]) -> int:
    agora = datetime.now(BRT)
    saida = PASTA_SQL.parent / "medicoes" / agora.strftime("%Y-%m-%d")
    saida.mkdir(parents=True, exist_ok=True)
    cliente = bigquery.Client(project=PROJETO)
    falhas = 0
    for arquivo in sorted(PASTA_SQL.glob("q*.sql")):
        if filtros and not any(arquivo.stem.startswith(f) for f in filtros):
            continue
        sql = renderizar_sql(arquivo.read_text(encoding="utf-8"))
        if "@id_usuario" in sql:
            print(f"{arquivo.name}: pulada (por cliente; use medir_usuario.py)")
            continue
        parametros = [bigquery.ScalarQueryParameter("data_corte", "DATE", DATA_CORTE)] if "@data_corte" in sql else []
        try:
            job = cliente.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=parametros))
            linhas = [dict(linha) for linha in job.result()]
        except Exception as erro:  # a falha é o resultado: reporta e não grava
            print(f"{arquivo.name}: NAO_MEDIDO ({type(erro).__name__}: {erro})", file=sys.stderr)
            falhas += 1
            continue
        selo = {
            "consulta": arquivo.name,
            "fonte": TABELA,
            "medido_em": agora.strftime("%Y-%m-%dT%H:%M BRT"),
            "autenticacao": "ADC",
            "job_id": job.job_id,
            "bytes_processados": job.total_bytes_processed,
            "linhas": linhas,
        }
        destino = saida / f"{arquivo.stem}.json"
        destino.write_text(json.dumps(selo, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"{arquivo.name}: {len(linhas)} linhas -> {destino.relative_to(PASTA_SQL.parents[2])}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(medir(sys.argv[1:]))
