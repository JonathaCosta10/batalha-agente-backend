"""A base é realmente lida? Consulta NOVA ao BigQuery (use_query_cache=False) e comparação com o CSV da verdade.

Uso (na pasta backend-agente-conversacional):
    ..\\frontend-agent-conversacional\\.venv\\Scripts\\python.exe scripts/verificar_base_lida.py

Grava relatorios/contratos/base-lida-<AAAA-MM-DDTHHMM>.json com: job_id, bytes, hora BRT, linhas, id_usuario
distintos, min/max anomes, e a comparação dos 1000 id com data/usuarios_verdade.csv (conjunto e sha256 do .selo.json).
Se o BigQuery falhar, grava estado NAO_MEDIDO com o erro: nunca números.
"""
import csv
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parents[1]
BRT = ZoneInfo('America/Sao_Paulo')
PROJETO = 'batalha-time-02-lxof'
TABELA = f'{PROJETO}.hackathon_dados.extrato_sintetico'
SQL = f"""
SELECT COUNT(*) AS linhas, COUNT(DISTINCT id_usuario) AS usuarios_distintos,
       MIN(anomes) AS anomes_min, MAX(anomes) AS anomes_max,
       TO_HEX(SHA256(STRING_AGG(DISTINCT id_usuario, ',' ORDER BY id_usuario))) AS sha256_ids
FROM `{TABELA}`
"""
SQL_IDS = f'SELECT DISTINCT id_usuario FROM `{TABELA}` ORDER BY id_usuario'


def medir():
    from google.cloud import bigquery
    cliente = bigquery.Client(project=PROJETO)
    cfg = bigquery.QueryJobConfig(use_query_cache=False)
    saida = {}
    for nome, sql in (('agregado', SQL), ('ids', SQL_IDS)):
        inicio = time.perf_counter()
        job = cliente.query(sql, job_config=cfg)
        linhas = [dict(l) for l in job.result()]
        saida[nome] = {'job_id': job.job_id, 'bytes_processados': job.total_bytes_processed,
                       'cache_hit': job.cache_hit, 'tempo_ms': round((time.perf_counter() - inicio) * 1000, 1),
                       'medido_em': datetime.now(BRT).isoformat(timespec='seconds'), 'linhas': linhas}
    return saida


def main():
    agora = datetime.now(BRT)
    selo_csv = json.loads((RAIZ / 'data' / 'usuarios_verdade.selo.json').read_text(encoding='utf-8'))
    arq_csv = RAIZ / 'data' / 'usuarios_verdade.csv'
    sha_arquivo = hashlib.sha256(arq_csv.read_bytes()).hexdigest()
    with arq_csv.open(encoding='utf-8') as f:
        ids_csv = [l['id_usuario'] for l in csv.DictReader(f)]
    rel = {'gerado_em': agora.isoformat(timespec='seconds'), 'gerado_por': 'scripts/verificar_base_lida.py',
           'fonte': TABELA, 'autenticacao': 'ADC',
           'csv': {'arquivo': 'data/usuarios_verdade.csv', 'linhas': len(ids_csv),
                   'sha256_arquivo': sha_arquivo, 'sha256_selo': selo_csv.get('sha256'),
                   'sha256_bate_com_selo': sha_arquivo == selo_csv.get('sha256')}}
    try:
        med = medir()
    except Exception as erro:  # sem ADC, rede ou permissão
        rel.update(estado='NAO_MEDIDO', erro=f'{type(erro).__name__}: {erro}'[:500])
    else:
        ag = med['agregado']['linhas'][0]
        ids_bq = [l['id_usuario'] for l in med['ids']['linhas']]
        rel.update(estado='MEDIDO', consulta={k: {kk: vv for kk, vv in v.items() if kk != 'linhas'} for k, v in med.items()},
                   base={'linhas': ag['linhas'], 'usuarios_distintos': ag['usuarios_distintos'],
                         'anomes_min': ag['anomes_min'], 'anomes_max': ag['anomes_max'],
                         'sha256_ids_ordenados': ag['sha256_ids']},
                   comparacao={'ids_bq': len(ids_bq), 'ids_csv': len(ids_csv),
                               'mesmo_conjunto': set(ids_bq) == set(ids_csv),
                               'mesma_ordem_indice': ids_bq == ids_csv,
                               'so_no_bq': sorted(set(ids_bq) - set(ids_csv))[:10],
                               'so_no_csv': sorted(set(ids_csv) - set(ids_bq))[:10]})
    pasta = RAIZ / 'relatorios' / 'contratos'
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f'base-lida-{agora.strftime("%Y-%m-%dT%H%M")}.json'
    destino.write_text(json.dumps(rel, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(json.dumps(rel, ensure_ascii=False, indent=1, default=str))
    print('gravado', destino)
    return 0 if rel['estado'] == 'MEDIDO' else 2


if __name__ == '__main__':
    sys.exit(main())
