-- Visão categoria: uma macro de saída do cliente (@categoria validada contra t3.MAPA_GRUPOS antes de rodar).
SELECT
  @categoria AS categoria,
  (SELECT grupo FROM grupos WHERE macro = @categoria) AS grupo,
  COUNTIF(tipo = 'S' AND macro = @categoria) AS lancamentos,
  ROUND(SUM(IF(tipo = 'S' AND macro = @categoria, valor, 0)), 2) AS total,
  ROUND(SAFE_DIVIDE(SUM(IF(tipo = 'S' AND macro = @categoria, valor, 0)), COUNT(DISTINCT anomes)), 2) AS media_mensal,
  ROUND(SAFE_DIVIDE(SUM(IF(tipo = 'S' AND macro = @categoria, valor, 0)), SUM(IF(tipo = 'S', valor, 0))) * 100, 2) AS pct_do_outflow,
  COUNT(DISTINCT anomes) AS meses
FROM mov
