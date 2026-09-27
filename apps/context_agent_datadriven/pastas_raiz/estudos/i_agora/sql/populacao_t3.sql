-- População T3: uma linha por cliente com as médias mensais que a regra T3 usa.
-- Mesma janela e mesmo mapa das visões por cliente; a classificação é feita por t3.classificar_t3.
WITH {{GRUPOS}},
mov AS (
  SELECT e.id_usuario, e.anomes, e.tipo, ABS(e.vlr) AS valor, g.grupo
  FROM `batalha-time-02-lxof.hackathon_dados.extrato_sintetico` AS e
  LEFT JOIN grupos AS g
    ON g.macro = e.nom_cate_macro AND e.tipo = 'S'
  WHERE e.anomes < CAST(FORMAT_DATE('%Y%m', @data_corte) AS INT64)
),
mensal AS (
  SELECT
    id_usuario,
    anomes,
    SUM(IF(tipo = 'E', valor, 0)) AS inflow,
    SUM(IF(tipo = 'S', valor, 0)) AS outflow,
    SUM(IF(grupo = 'essencial', valor, 0)) AS essencial,
    SUM(IF(grupo = 'compromisso_financeiro', valor, 0)) AS compromisso,
    SUM(IF(grupo = 'discricionario', valor, 0)) AS discricionario,
    SUM(IF(grupo = 'nao_classificado', valor, 0)) AS nao_classificado,
    COUNTIF(tipo = 'S' AND grupo IS NULL) AS saidas_sem_grupo
  FROM mov
  GROUP BY id_usuario, anomes
)
SELECT
  id_usuario,
  COUNT(*) AS meses,
  AVG(inflow) AS inflow,
  AVG(outflow) AS outflow,
  AVG(essencial) AS essencial,
  AVG(compromisso) AS compromisso,
  AVG(discricionario) AS discricionario,
  AVG(nao_classificado) AS nao_classificado,
  SAFE_DIVIDE(STDDEV_SAMP(inflow), AVG(inflow)) AS cv_inflow,
  SUM(saidas_sem_grupo) AS saidas_sem_grupo
FROM mensal
GROUP BY id_usuario
