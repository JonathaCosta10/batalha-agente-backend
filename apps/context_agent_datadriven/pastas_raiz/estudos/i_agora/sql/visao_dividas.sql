-- Visão dividas: compromisso financeiro (empréstimos, fatura, juros, boletos) e quanto do Inflow ele consome.
SELECT
  ROUND(SUM(IF(grupo = 'compromisso_financeiro', valor, 0)), 2) AS compromisso_total,
  ROUND(SAFE_DIVIDE(SUM(IF(grupo = 'compromisso_financeiro', valor, 0)), COUNT(DISTINCT anomes)), 2) AS compromisso_mensal,
  ROUND(SUM(IF(tipo = 'S' AND micro = 'Pagamento de fatura', valor, 0)), 2) AS fatura_total,
  ROUND(SUM(IF(tipo = 'S' AND macro = 'Emprestimos e financiamentos', valor, 0)), 2) AS emprestimos_financiamentos_total,
  ROUND(SUM(IF(tipo = 'S' AND micro = 'Juros pagos', valor, 0)), 2) AS juros_pagos_total,
  COUNTIF(tipo = 'S' AND micro IN ('Multa por atraso', 'Multa')) AS multas,
  COUNTIF(parcela_total IS NOT NULL) AS lancamentos_parcelados,
  ROUND(SAFE_DIVIDE(SUM(IF(grupo = 'compromisso_financeiro', valor, 0)), SUM(IF(tipo = 'E', valor, 0))) * 100, 2) AS pct_inflow_comprometido
FROM mov
