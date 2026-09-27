-- q05 · Perfil de renda por vínculo e faixa salarial (células 5-10, 21 e 31) sobre a base real
-- Vínculo: 'SÓ CLT' se o cliente tem alguma entrada micro 'Salario CLT' e nenhuma 'Recebimentos diversos';
--          'SÓ AUTÔNOMO' no inverso; 'MISTO' com as duas; 'OUTRA' sem nenhuma.
-- Faixa: média mensal de entradas (todas as micros de tipo E).
WITH por_cliente AS (
  SELECT
    id_usuario,
    COUNTIF(tipo = 'E' AND nom_cate_micro = 'Salario CLT')           AS n_clt,
    COUNTIF(tipo = 'E' AND nom_cate_micro = 'Recebimentos diversos') AS n_diversos,
    SUM(IF(tipo = 'E', ABS(vlr), 0)) / COUNT(DISTINCT anomes)         AS renda_media_mensal
  FROM `batalha-time-02-lxof.hackathon_dados.extrato_sintetico`
  GROUP BY id_usuario
),
classe AS (
  SELECT *,
    CASE WHEN n_clt > 0 AND n_diversos = 0 THEN 'SÓ CLT'
         WHEN n_clt = 0 AND n_diversos > 0 THEN 'SÓ AUTÔNOMO'
         WHEN n_clt > 0 AND n_diversos > 0 THEN 'MISTO'
         ELSE 'OUTRA' END AS vinculo,
    CASE WHEN renda_media_mensal <= 2500 THEN '1. Até R$ 2.500'
         WHEN renda_media_mensal <= 5000 THEN '2. R$ 2.501 a R$ 5.000'
         WHEN renda_media_mensal <= 10000 THEN '3. R$ 5.001 a R$ 10.000'
         ELSE '4. Acima de R$ 10.000' END AS faixa_salarial
  FROM por_cliente
)
SELECT vinculo, faixa_salarial, COUNT(*) AS clientes,
       ROUND(AVG(renda_media_mensal), 2) AS renda_media_mensal,
       ROUND(STDDEV(renda_media_mensal), 2) AS desvio_renda_entre_clientes
FROM classe
GROUP BY vinculo, faixa_salarial
ORDER BY vinculo, faixa_salarial
