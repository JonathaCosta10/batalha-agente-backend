"""Snapshot do último mês encerrado de um id_usuario, lido do extrato no BigQuery.

Portado de Frontend/agent_backend/planning/bigquery.py (2026-09-27). Mudanças:
- a consulta roda pelo executor que este backend já usa (usuario_real._novo_executor -> visoes.ExecutorBigQuery:
  ADC, dry-run primeiro, teto de bytes, parâmetros nomeados), em vez de uma sessão HTTP própria;
- o catálogo de id_usuario é o CSV da verdade (data/usuarios_verdade.csv, os mesmos 1.000 ids da tabela), sem
  consulta extra; as colunas são as verificadas no agent_backend (bq_mapping.json: id_usuario, anomes, vlr,
  nom_cate_macro, tipo E/S);
- USUARIO_REAL['ATIVO']=False desliga também esta fonte (503 NAO_MEDIDO, nunca base fictícia).
"""
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal

from django.conf import settings

TABELA = 'batalha-time-02-lxof.hackathon_dados.extrato_sintetico'
_PERIODO = "CONCAT(SUBSTR(REPLACE(CAST(anomes AS STRING), '-', ''), 1, 4), '-', SUBSTR(REPLACE(CAST(anomes AS STRING), '-', ''), 5, 2))"
SQL_SNAPSHOT = f"""
WITH movements AS (
  SELECT {_PERIODO} AS period, CAST(nom_cate_macro AS STRING) AS category, SAFE_CAST(vlr AS NUMERIC) AS amount,
         LOWER(CAST(tipo AS STRING)) = 'e' AS is_in, LOWER(CAST(tipo AS STRING)) = 's' AS is_out
  FROM `{TABELA}`
  WHERE CAST(id_usuario AS STRING) = @customer AND {_PERIODO} < @cutoff)
SELECT period, category,
       CAST(SUM(IF(is_in, ABS(amount), 0)) AS STRING) AS inflows,
       CAST(SUM(IF(is_out, ABS(amount), 0)) AS STRING) AS outflows,
       COUNTIF(amount IS NULL OR NOT (COALESCE(is_in, FALSE) OR COALESCE(is_out, FALSE))) AS invalid
FROM movements WHERE period = (SELECT MAX(period) FROM movements)
GROUP BY period, category
"""


class SourceUnavailable(RuntimeError):
    pass


class FonteExtrato:
    """Mesmo contrato do BigQuerySource do agent_backend: customers() e load_ref(ref)."""

    def __init__(self, executor_factory=None):
        self._executor_factory = executor_factory
        self._cache = {}
        self._trava = threading.Lock()

    def _executor(self):
        if self._executor_factory:
            return self._executor_factory()
        from apps.context_agent_datadriven.services import usuario_real
        return usuario_real._novo_executor()

    def _ttl(self):
        return getattr(settings, 'USUARIO_REAL', {}).get('CACHE_SEGUNDOS', 900)

    def customers(self):
        """id_usuario do CSV da verdade, ordenados (a posição é só o índice do catálogo)."""
        from apps.context_agent_datadriven.services import perfil_usuario
        try:
            return sorted(perfil_usuario._carregar()['por_uuid'])
        except perfil_usuario.BaseAusente as e:
            raise SourceUnavailable(str(e)) from None

    def load(self, index=1):
        users = self.customers()
        if not users:
            raise SourceUnavailable('Nenhum cliente em mês encerrado foi encontrado.')
        return self.load_ref(users[(index - 1) % len(users)])

    def load_ref(self, ref):
        if not getattr(settings, 'USUARIO_REAL', {}).get('ATIVO', True):
            raise SourceUnavailable('Fonte do extrato desligada (USUARIO_REAL_ATIVO=0); nenhuma base fictícia foi usada.')
        users = self.customers()
        if ref not in users:
            raise SourceUnavailable('Cliente sorteado não está no catálogo.')
        with self._trava:
            item = self._cache.get(ref)
        if item and time.monotonic() - item[0] < self._ttl():
            return {**item[1], 'seal': {**item[1]['seal'], 'cache': True}}
        executor = self._executor()
        try:
            rows = executor.executar(SQL_SNAPSHOT, {'customer': ref,
                                                    'cutoff': datetime.now(timezone.utc).strftime('%Y-%m')})
        except Exception:
            raise SourceUnavailable('BigQuery indisponível; nenhuma base fictícia foi substituída.') from None
        if not rows or any(int(r['invalid']) for r in rows):
            raise SourceUnavailable('Dados ausentes ou movimentos sem direção/valor válidos.')
        periods = {r['period'] for r in rows}
        if len(periods) != 1:
            raise SourceUnavailable('Períodos não reconciliados.')
        job = getattr(executor, 'ultimo_job', {}) or {}
        seal = {'source': TABELA, 'nature': 'sintetica', 'measuredAt': datetime.now(timezone.utc).isoformat(),
                'cache': False, 'bytesProcessed': job.get('bytes_processados'), 'jobId': job.get('job_id')}
        # Categorias preservadas; o agrupamento semântico é do domain.from_snapshot.
        result = {'client_ref': ref, 'index': users.index(ref) + 1, 'reference_month': next(iter(periods)),
                  'inflows': str(sum((Decimal(r['inflows']) for r in rows), Decimal(0)).quantize(Decimal('.01'))),
                  'outflows': str(sum((Decimal(r['outflows']) for r in rows), Decimal(0)).quantize(Decimal('.01'))),
                  'categories': {r['category'] or 'Sem categoria': r['outflows'] for r in rows}, 'seal': seal}
        with self._trava:
            self._cache[ref] = (time.monotonic(), result)
        return result
