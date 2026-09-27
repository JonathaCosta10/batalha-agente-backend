-- q06 · Composição das saídas por macro categoria (Passo 1.2, célula 33) sobre a base real
-- Contrapõe "Casa/Essencial 43,9% · Flexível/Delivery 39,6% · Supérfluo 11,0% · Banco/Taxas 5,5%" (sintético).
SELECT
  nom_cate_macro,
  COUNT(*)                                                     AS registros,
  ROUND(SUM(ABS(vlr)), 2)                                      AS soma_abs_vlr,
  ROUND(SUM(ABS(vlr)) / SUM(SUM(ABS(vlr))) OVER () * 100, 2)   AS pct_das_saidas
FROM `batalha-time-02-lxof.hackathon_dados.extrato_sintetico`
WHERE tipo = 'S'
GROUP BY nom_cate_macro
ORDER BY pct_das_saidas DESC
