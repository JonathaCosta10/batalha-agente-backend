-- q04 · Coorte negativada em dezembro/2025 e sua evolução no ano ("Tesoura de Liquidez")
-- Coorte = clientes com entradas - saídas < 0 em anomes 202512 (regra das células 25/27/31/36).
-- Devolve uma linha por mês com as médias da coorte; tamanho da coorte e base total em cada linha.
-- Atenção: dezembro só vai até a última data da base (ver q01.ultima_data).
WITH mensal AS (
  SELECT id_usuario, anomes,
         SUM(IF(tipo = 'E', ABS(vlr), 0)) AS entradas,
         SUM(IF(tipo = 'S', ABS(vlr), 0)) AS saidas
  FROM `batalha-time-02-lxof.hackathon_dados.extrato_sintetico`
  GROUP BY id_usuario, anomes
),
coorte AS (
  SELECT id_usuario, saidas - entradas AS divida_dezembro
  FROM mensal
  WHERE anomes = 202512 AND entradas - saidas < 0
)
SELECT
  m.anomes,
  (SELECT COUNT(*) FROM coorte)                              AS clientes_coorte,
  (SELECT COUNT(DISTINCT id_usuario) FROM mensal)            AS clientes_base,
  ROUND((SELECT AVG(divida_dezembro) FROM coorte), 2)        AS divida_media_dezembro,
  ROUND((SELECT APPROX_QUANTILES(divida_dezembro, 2)[OFFSET(1)] FROM coorte), 2) AS divida_mediana_dezembro,
  COUNT(*)                                                   AS clientes_com_movimento_no_mes,
  ROUND(AVG(m.entradas), 2)                                  AS entradas_medias,
  ROUND(AVG(m.saidas), 2)                                    AS saidas_medias,
  ROUND(AVG(m.entradas - m.saidas), 2)                       AS saldo_medio
FROM mensal m
JOIN coorte c USING (id_usuario)
GROUP BY m.anomes
ORDER BY m.anomes
