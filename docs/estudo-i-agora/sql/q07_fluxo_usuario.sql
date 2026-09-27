-- Pergunta dirigida: como evoluiu o fluxo de um único usuário até a data de corte?
-- Parâmetros BigQuery: @id_usuario STRING, @data_corte DATE.
-- A data é interpretada em America/Sao_Paulo. Nenhum outro usuário entra no contexto.
WITH movimentos AS (
  SELECT anomesdia,
         EXTRACT(YEAR FROM DATE(anomesdia, 'America/Sao_Paulo')) * 100 +
         EXTRACT(MONTH FROM DATE(anomesdia, 'America/Sao_Paulo')) AS anomes,
         tipo, vlr, nom_cate_macro
  FROM `batalha-time-02-lxof.hackathon_dados.extrato_sintetico`
  WHERE id_usuario = @id_usuario
    AND DATE(anomesdia, 'America/Sao_Paulo') <= @data_corte
),
mensal AS (
  SELECT anomes,
         COUNT(*) AS movimentos,
         ROUND(SUM(IF(tipo = 'E', ABS(vlr), 0)), 2) AS entradas,
         ROUND(SUM(IF(tipo = 'S', ABS(vlr), 0)), 2) AS saidas,
         ROUND(SUM(IF(tipo = 'E', ABS(vlr), -ABS(vlr))), 2) AS saldo
  FROM movimentos
  GROUP BY anomes
),
categorias AS (
  SELECT nom_cate_macro AS categoria,
         COUNT(*) AS movimentos,
         ROUND(SUM(ABS(vlr)), 2) AS total_saida
  FROM movimentos
  WHERE tipo = 'S'
  GROUP BY nom_cate_macro
)
SELECT
  COUNT(*) AS total_movimentos,
  COUNTIF(tipo = 'E') AS movimentos_entrada,
  COUNTIF(tipo = 'S') AS movimentos_saida,
  MIN(anomesdia) AS primeira_movimentacao,
  MAX(anomesdia) AS ultima_movimentacao,
  ROUND(SUM(IF(tipo = 'E', ABS(vlr), 0)), 2) AS entradas_total,
  ROUND(SUM(IF(tipo = 'S', ABS(vlr), 0)), 2) AS saidas_total,
  ROUND(SUM(IF(tipo = 'E', ABS(vlr), -ABS(vlr))), 2) AS saldo_periodo,
  ARRAY(SELECT AS STRUCT * FROM mensal ORDER BY anomes) AS meses,
  ARRAY(SELECT AS STRUCT * FROM categorias ORDER BY total_saida DESC LIMIT 5) AS categorias_saida
FROM movimentos
