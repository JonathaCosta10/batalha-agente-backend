-- Visão discricionario: onde está a folga do Esbanjador (maior categoria e média mensal do grupo).
, cat AS (
  SELECT macro, SUM(valor) AS total
  FROM mov
  WHERE grupo = 'discricionario'
  GROUP BY macro
)
SELECT
  (SELECT macro FROM cat ORDER BY total DESC, macro LIMIT 1) AS maior_categoria_discricionaria,
  (SELECT ROUND(MAX(total), 2) FROM cat) AS maior_categoria_total,
  ROUND(SAFE_DIVIDE((SELECT SUM(total) FROM cat), (SELECT COUNT(DISTINCT anomes) FROM mov)), 2) AS discricionario_mensal,
  (SELECT COUNT(*) FROM cat) AS categorias_discricionarias
