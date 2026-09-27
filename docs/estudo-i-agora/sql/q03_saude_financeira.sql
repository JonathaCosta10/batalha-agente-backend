-- q03 · Três grupos de saúde financeira (regra das células 13/31/33) sobre a base real
-- Mensal por cliente: entradas = soma |vlr| de tipo E; saídas = soma |vlr| de tipo S.
-- Perfil anual = média dos meses; grupo: saldo < 0 → Endividado; sobra < 15% → Vulnerável; senão Saudável.
-- Contrapõe as porcentagens sintéticas do notebook (42,15/23,36/34,49; 0,7/34,0/65,3; 11,0/29,5/59,5).
WITH mensal AS (
  SELECT
    id_usuario,
    anomes,
    SUM(IF(tipo = 'E', ABS(vlr), 0)) AS entradas,
    SUM(IF(tipo = 'S', ABS(vlr), 0)) AS saidas
  FROM `batalha-time-02-lxof.hackathon_dados.extrato_sintetico`
  GROUP BY id_usuario, anomes
),
mensal_calc AS (
  SELECT *, entradas - saidas AS saldo,
         IF(entradas > 0, (entradas - saidas) / entradas * 100, 0) AS pct_sobra
  FROM mensal
),
perfil AS (
  SELECT id_usuario, COUNT(*) AS meses, AVG(entradas) AS entradas, AVG(saidas) AS saidas,
         AVG(saldo) AS saldo, AVG(pct_sobra) AS pct_sobra
  FROM mensal_calc
  GROUP BY id_usuario
),
grupo AS (
  SELECT *,
    CASE WHEN saldo < 0 THEN '1. Endividado (< 0)'
         WHEN pct_sobra < 15 THEN '2. Vulnerável (< 15%)'
         ELSE '3. Saudável (>= 15%)' END AS cluster_financeiro
  FROM perfil
)
SELECT
  cluster_financeiro,
  COUNT(*)                                           AS clientes,
  ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2)   AS pct_base,
  ROUND(AVG(entradas), 2)                            AS entrada_media_mensal,
  ROUND(AVG(saidas), 2)                              AS saida_media_mensal,
  ROUND(AVG(saldo), 2)                               AS saldo_medio_mensal,
  ROUND(AVG(pct_sobra), 2)                           AS pct_sobra_medio,
  ROUND(AVG(meses), 2)                               AS meses_medios
FROM grupo
GROUP BY cluster_financeiro
ORDER BY cluster_financeiro
