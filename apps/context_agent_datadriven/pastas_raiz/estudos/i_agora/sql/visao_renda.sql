-- Visão renda: fontes de entrada e volatilidade do Inflow mensal (coeficiente de variação).
, mensal AS (
  SELECT anomes, SUM(IF(tipo = 'E', valor, 0)) AS inflow
  FROM mov
  GROUP BY anomes
)
SELECT
  ROUND(SUM(IF(tipo = 'E' AND micro = 'Salario CLT', valor, 0)), 2) AS salario_clt_total,
  ROUND(SUM(IF(tipo = 'E' AND micro = 'Recebimentos diversos', valor, 0)), 2) AS recebimentos_diversos_total,
  ROUND(SUM(IF(tipo = 'E' AND micro NOT IN ('Salario CLT', 'Recebimentos diversos'), valor, 0)), 2) AS outras_entradas_total,
  ROUND(SUM(IF(tipo = 'E', valor, 0)), 2) AS inflow_total,
  (SELECT ROUND(AVG(inflow), 2) FROM mensal) AS inflow_mensal,
  (SELECT ROUND(SAFE_DIVIDE(STDDEV_SAMP(inflow), AVG(inflow)) * 100, 2) FROM mensal) AS volatilidade_inflow_pct,
  (SELECT COUNT(*) FROM mensal) AS meses
FROM mov
