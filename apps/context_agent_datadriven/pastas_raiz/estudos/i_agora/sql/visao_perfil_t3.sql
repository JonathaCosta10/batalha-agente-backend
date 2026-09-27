-- Visão perfil_t3: Inflow / Outflow / Surplus mensais, grupos de saída e segmento T3.
, mensal AS (
  SELECT
    anomes,
    SUM(IF(tipo = 'E', valor, 0)) AS inflow,
    SUM(IF(tipo = 'S', valor, 0)) AS outflow,
    SUM(IF(grupo = 'essencial', valor, 0)) AS essencial,
    SUM(IF(grupo = 'compromisso_financeiro', valor, 0)) AS compromisso,
    SUM(IF(grupo = 'discricionario', valor, 0)) AS discricionario,
    SUM(IF(grupo = 'nao_classificado', valor, 0)) AS nao_classificado
  FROM mov
  GROUP BY anomes
)
SELECT
  COUNT(*) AS meses,
  ROUND(AVG(inflow), 2) AS inflow_mensal,
  ROUND(AVG(outflow), 2) AS outflow_mensal,
  ROUND(AVG(inflow) - AVG(outflow), 2) AS surplus_mensal,
  ROUND(SAFE_DIVIDE(AVG(inflow) - AVG(outflow), AVG(inflow)) * 100, 2) AS taxa_surplus_pct,
  ROUND(AVG(essencial), 2) AS essencial_mensal,
  ROUND(AVG(compromisso), 2) AS compromisso_mensal,
  ROUND(AVG(discricionario), 2) AS discricionario_mensal,
  ROUND(AVG(nao_classificado), 2) AS nao_classificado_mensal,
  (SELECT COUNTIF(tipo = 'S' AND grupo IS NULL) FROM mov) AS saidas_sem_grupo,
  CASE
    WHEN COUNT(*) = 0 OR AVG(inflow) <= 0 THEN 'Vulnerável'
    WHEN (AVG(inflow) - AVG(outflow)) / AVG(inflow) >= {{LIMIAR_SURPLUS}} THEN 'Livre'
    WHEN (AVG(inflow) - AVG(outflow) + AVG(discricionario)) / AVG(inflow) >= {{LIMIAR_SURPLUS}} THEN 'Esbanjador'
    ELSE 'Vulnerável'
  END AS segmento_t3
FROM mensal
