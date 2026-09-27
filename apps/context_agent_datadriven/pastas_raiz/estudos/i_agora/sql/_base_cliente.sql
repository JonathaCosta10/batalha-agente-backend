-- Prefixo comum das visões por cliente (visoes.py junta este arquivo ao SELECT da visão).
-- mov: movimentos de UM cliente nos meses completos antes do mês do corte.
-- Saída sem grupo no mapa fica com grupo NULL e é contada em saidas_sem_grupo (o guard exige 0).
WITH {{GRUPOS}},
mov AS (
  SELECT
    e.anomes,
    e.anomesdia,
    e.tipo,
    ABS(e.vlr) AS valor,
    e.nom_cate_macro AS macro,
    IFNULL(e.nom_cate_micro, '') AS micro,
    e.descr,
    e.parcela_total,
    g.grupo
  FROM `batalha-time-02-lxof.hackathon_dados.extrato_sintetico` AS e
  LEFT JOIN grupos AS g
    ON g.macro = e.nom_cate_macro AND e.tipo = 'S'
  WHERE e.id_usuario = @id_usuario
    AND e.anomes < CAST(FORMAT_DATE('%Y%m', @data_corte) AS INT64)
)
