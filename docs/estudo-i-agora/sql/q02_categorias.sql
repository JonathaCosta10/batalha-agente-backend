-- q02 · Taxonomia real: contagem e valor por tipo, macro e micro
-- Contrapõe o fallback das células 22/23 (ex.: "Recebimentos diversos 18.363", "Salario CLT 9.600").
SELECT
  tipo,
  nom_cate_macro,
  nom_cate_micro,
  COUNT(*)                      AS registros,
  COUNT(DISTINCT id_usuario)    AS clientes,
  ROUND(SUM(ABS(vlr)), 2)       AS soma_abs_vlr,
  ROUND(AVG(ABS(vlr)), 2)       AS media_abs_vlr
FROM `batalha-time-02-lxof.hackathon_dados.extrato_sintetico`
GROUP BY tipo, nom_cate_macro, nom_cate_micro
ORDER BY tipo, registros DESC
