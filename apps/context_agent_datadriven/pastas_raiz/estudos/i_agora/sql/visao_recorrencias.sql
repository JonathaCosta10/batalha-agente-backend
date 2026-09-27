-- Visão recorrencias: assinaturas do cliente (lançamentos, total, média mensal e serviços distintos por descr).
SELECT
  COUNTIF(tipo = 'S' AND macro = 'Assinaturas') AS lancamentos_assinaturas,
  ROUND(SUM(IF(tipo = 'S' AND macro = 'Assinaturas', valor, 0)), 2) AS assinaturas_total,
  ROUND(SAFE_DIVIDE(SUM(IF(tipo = 'S' AND macro = 'Assinaturas', valor, 0)), COUNT(DISTINCT anomes)), 2) AS assinaturas_mensal,
  COUNT(DISTINCT IF(tipo = 'S' AND macro = 'Assinaturas', descr, NULL)) AS servicos_distintos
FROM mov
