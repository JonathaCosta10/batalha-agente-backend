-- q_spec_diagnostico · Atributos por cliente para testar a especificacao colada pelo dono (N=316, 48,4 % critico, T3 89,6/7,0/3,5).
-- Uma linha por id_usuario (1000). Os agregados sao feitos em Python (q_spec_diagnostico_medir.py); o JSON selado nao leva ids.
-- Inflow = soma ABS(vlr) com tipo='E'; Outflow = soma ABS(vlr) com tipo='S' (a base NAO tem coluna V/True: tipo e E/S).
-- Dezembro em duas leituras: mes inteiro (anomes=202512) e ate @data_corte (DATE(anomesdia) <= 2025-12-22).
WITH mov AS (
  SELECT id_usuario, anomes, DATE(anomesdia) AS dia, tipo, ABS(vlr) AS v, nom_cate_macro AS macro,
         nom_cate_micro AS micro, saldo_apos, parcela_total
  FROM `batalha-time-02-lxof.hackathon_dados.extrato_sintetico`
),
mes AS (
  SELECT id_usuario, anomes,
         SUM(IF(tipo = 'E', v, 0)) AS inflow,
         SUM(IF(tipo = 'S', v, 0)) AS outflow,
         SUM(IF(tipo = 'S' AND macro IN ('Lazer','Lojas e sites','Viagens','Restaurantes','Delivery','Assinaturas',
                                         'Cuidados pessoais','Transporte por app','Pets'), v, 0)) AS discricionario,
         SUM(IF(tipo = 'S' AND micro IN ('Juros pagos','Outras tarifas financeiras','Anuidade e pacote de servico',
                                         'Multa por atraso'), v, 0)) AS divida_cara
  FROM mov GROUP BY id_usuario, anomes
),
ano AS (
  SELECT id_usuario,
         COUNT(*) AS meses,
         COUNTIF(inflow > 0 AND (inflow - outflow) / inflow >= 0.15) AS meses_margem15_12m,
         COUNTIF(anomes < 202512 AND inflow > 0 AND (inflow - outflow) / inflow >= 0.15) AS meses_margem15_janov,
         COUNTIF(inflow - outflow < 0) AS meses_deficit_12m,
         AVG(IF(anomes < 202512, inflow, NULL))  AS inflow_medio_janov,
         AVG(IF(anomes < 202512, outflow, NULL)) AS outflow_medio_janov,
         AVG(IF(anomes < 202512, discricionario, NULL)) AS discricionario_medio_janov,
         SUM(inflow) AS inflow_12m, SUM(outflow) AS outflow_12m, SUM(divida_cara) AS divida_cara_12m,
         MAX(IF(anomes = 202512, inflow, NULL))  AS dez_inflow,
         MAX(IF(anomes = 202512, outflow, NULL)) AS dez_outflow,
         MAX(IF(anomes = 202512, discricionario, NULL)) AS dez_discricionario
  FROM mes GROUP BY id_usuario
),
flags AS (
  SELECT id_usuario,
         SUM(IF(anomes = 202512 AND dia <= @data_corte AND tipo = 'E', v, 0)) AS dez22_inflow,
         SUM(IF(anomes = 202512 AND dia <= @data_corte AND tipo = 'S', v, 0)) AS dez22_outflow,
         COUNTIF(anomes = 202512) AS transacoes_dez,
         COUNTIF(micro = 'Juros pagos') AS n_juros,
         COUNTIF(micro = 'Juros pagos' AND anomes = 202512) AS n_juros_dez,
         COUNTIF(micro = 'Cheque') AS n_cheque,
         COUNTIF(micro IN ('Outras tarifas financeiras','Multa por atraso')) AS n_tarifa_multa,
         COUNTIF(micro IN ('Emprestimos','Outros emprestimos')) AS n_emprestimo,
         COUNTIF(micro = 'Financiamento de imovel') AS n_financiamento_imovel,
         COUNTIF(micro = 'Consorcio') AS n_consorcio,
         COUNTIF(saldo_apos < 0) AS n_saldo_negativo,
         COUNTIF(saldo_apos < 0 AND anomes = 202512) AS n_saldo_negativo_dez,
         MIN(saldo_apos) AS saldo_minimo,
         COUNTIF(micro = 'Salario CLT') AS n_clt,
         COUNTIF(micro = 'Beneficio INSS') AS n_inss,
         COUNTIF(micro = 'Recebimento Aluguel') AS n_aluguel_recebido,
         COUNTIF(micro = 'Pagamento de aluguel') AS n_aluguel_pago,
         COUNTIF(micro = 'Bonus PLR') AS n_plr,
         COUNTIF(parcela_total > 1) AS n_parcelado
  FROM mov GROUP BY id_usuario
),
serie AS (
  SELECT id_usuario, ARRAY_AGG(STRUCT(anomes, inflow, outflow) ORDER BY anomes) AS meses_serie
  FROM mes GROUP BY id_usuario
),
dias AS (
  SELECT id_usuario, ARRAY_AGG(STRUCT(dia, e, s) ORDER BY dia) AS dez_dias
  FROM (SELECT id_usuario, EXTRACT(DAY FROM dia) AS dia, SUM(IF(tipo = 'E', v, 0)) AS e, SUM(IF(tipo = 'S', v, 0)) AS s
        FROM mov WHERE anomes = 202512 GROUP BY id_usuario, dia)
  GROUP BY id_usuario
)
SELECT a.*, f.* EXCEPT (id_usuario), s.meses_serie, d.dez_dias
FROM ano a JOIN flags f USING (id_usuario) JOIN serie s USING (id_usuario) LEFT JOIN dias d USING (id_usuario)
ORDER BY id_usuario
