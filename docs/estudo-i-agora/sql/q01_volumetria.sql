-- q01 · Volumetria e integridade da base real
-- Confere: nº de linhas, clientes, janela de datas, E/S, nulos e valores negativos.
-- Contrapõe o notebook (células 1-4: "150.000 registros, 6 colunas, 0 nulos").
SELECT
  COUNT(*)                                   AS linhas,
  COUNT(DISTINCT id_usuario)                 AS clientes,
  MIN(anomesdia)                             AS primeira_data,
  MAX(anomesdia)                             AS ultima_data,
  COUNT(DISTINCT anomes)                     AS meses_distintos,
  COUNTIF(tipo = 'E')                        AS linhas_entrada,
  COUNTIF(tipo = 'S')                        AS linhas_saida,
  COUNTIF(tipo NOT IN ('E', 'S') OR tipo IS NULL) AS linhas_tipo_fora_de_e_s,
  COUNTIF(vlr < 0)                           AS linhas_vlr_negativo,
  COUNTIF(id_usuario IS NULL)                AS nulos_id_usuario,
  COUNTIF(anomesdia IS NULL)                 AS nulos_anomesdia,
  COUNTIF(vlr IS NULL)                       AS nulos_vlr,
  COUNTIF(nom_cate_macro IS NULL)            AS nulos_macro,
  COUNTIF(parcela_total IS NOT NULL)         AS linhas_parceladas,
  COUNTIF(anomesdia > TIMESTAMP('2025-12-22 23:59:59', 'America/Sao_Paulo')) AS linhas_apos_corte_tese
FROM `batalha-time-02-lxof.hackathon_dados.extrato_sintetico`
