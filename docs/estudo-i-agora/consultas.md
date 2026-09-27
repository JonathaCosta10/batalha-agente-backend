# Catálogo de consultas do estudo i.agora

Cada consulta do notebook recebe um código `Cnn`, a célula de origem, a **fonte dos dados** que ela realmente usou e, quando existe, a medição equivalente na tabela real (`qNN`).

Fontes possíveis:

| Rótulo | Significado |
| --- | --- |
| `REAL` | Leu o CSV exportado do BigQuery na máquina da autora. |
| `FALLBACK` | O CSV não foi achado; usou contagens digitadas no código e sorteou valores. |
| `SINTETICO` | `np.random.seed(42)` gera a população; não lê dado nenhum. |
| `FIXO` | Tabela digitada à mão no código. |

Números marcados **medido** têm selo em `medicoes/2026-09-27/*.json` (tabela `batalha-time-02-lxof.hackathon_dados.extrato_sintetico`, 2026-09-27 03:5x BRT, ADC). Os demais são do notebook e **não servem de fundamento**.

---

## Base

### C01 · Carga e integridade — células 1-4 · fonte `REAL` (estado anterior do kernel)

- **Consulta:** `pd.read_csv(bq-results-20260926-143453-1790433308679.csv)`, `info()`, `describe()`, `isnull().sum()`.
- **Notebook diz:** 150.000 linhas, 6 colunas (`id_usuario, mes, tipo, macro, valor, valor_direcional`), 0 nulos, meses 1-12, IDs `CLT_0000`.
- **Aviso:** a própria célula imprime "caminho não localizado". O `df` mostrado vem de uma execução anterior do kernel. O CSV não está no Drive nem neste repositório.
- **Medido (q01):** a tabela real tem **467.585 linhas, 1.000 clientes (UUID), 11 colunas**, de 2025-01-01 a 2025-12-31, 0 nulos nas colunas-chave, 35.077 entradas e 432.508 saídas, 29.847 linhas parceladas e **7.956 linhas depois do corte da tese (22/12/2025)**.
- **Conclusão:** a base de 150.000 linhas é um derivado de origem `NAO_VERIFICADA`. As macros dela (`Renda`, `Casa/Essencial`, `Flexivel/Delivery`, `Superfluo`, `Banco/Taxas`) não existem na tabela real.

### C02 · Composição por macro e tipo — célula 3 · fonte `REAL` (derivado)

- **Consulta:** `df.groupby(["macro","tipo"]).agg(count, sum, mean)`.
- **Notebook diz:** 30.000 linhas por macro; renda média 4.155,80.
- **Medido (q02):** 98 combinações tipo × macro × micro. Veja C03 para as entradas.

---

## Renda

### C03 · Taxonomia da renda — células 5-8, 22-23 · fonte `FIXO` / `FALLBACK`

- **Consulta:** contagens digitadas: Recebimentos diversos 18.363; Salário CLT 9.600; Aluguel 3.600; 13º 1.600; INSS 1.200; PLR 714.
- **Medido (q02):** as **seis contagens de entrada conferem exatamente**. O contexto muda a leitura: *Recebimentos diversos* aparece em **999 dos 1.000 clientes**, com média de R$ 1.819,82 por lançamento. *Salário CLT* aparece em 800 clientes, com média de R$ 5.490,48. Em valor, o CLT soma **R$ 52,7 mi** contra **R$ 33,4 mi** de diversos.
- **Saídas do fallback:** conferem *Mercado* 45.763 e *Restaurantes* 39.684, **no nível macro**. Não conferem *Energia elétrica* (fallback 15.000, real 12.000), *Pagamento de aluguel* (22.000 × 1.200), *Juros pagos* (12.000 × 4.755) e *Pagamento de fatura* (23.000 × 12.000).
- **Conclusão:** "gig economy lidera" mede **número de lançamentos**, não pessoas nem valor.

### C04 · Autônomos × CLT por faixa salarial — células 9-10, 21 · fonte `SINTETICO`

- **Consulta:** 15.000 rendas sorteadas: 65% autônomos N(3100, 1600) e 35% CLT N(4800, 1100). Depois `crosstab(faixa, perfil, normalize='columns')`.
- **Notebook diz:** até R$ 2.500 → 34,56% dos autônomos contra 1,69% dos CLT.
- **Medido (q05):** por cliente, **799 MISTO** (CLT + diversos), **200 SÓ AUTÔNOMO** e **1 SÓ CLT**. Nenhum cliente com renda média até R$ 2.500. Autônomos: 96 na faixa de R$ 2.501-5.000 e 104 na de R$ 5.001-10.000. Mistos: 300 acima de R$ 10.000.
- **Conclusão:** a divisão 65/35 e a concentração de autônomos na base de renda **não se sustentam** na tabela real.

---

## Saúde financeira

### C05 · Endividado × positivo — células 11-12 · fonte `SINTETICO`

- **Consulta:** 50.000 rendas `lognormal(8, 0.8)` × fator de gasto `N(0.95, 0.25)`; `saldo = renda − gasto`.
- **Notebook diz:** 42,15% negativos; buraco médio R$ −763,64; sobra média R$ 923,84.

### C06 · Três grupos (regra de 15%) — células 13-16, 31-34 · fonte `SINTETICO`

- **Regra (mantida em `consultas.classificar_saude`):** saldo < 0 → Endividado; sobra < 15% da renda → Vulnerável; senão Saudável.
- **Notebook diz, em três versões sintéticas diferentes:** 42,15/23,36/34,49 (c.13); 0,7/34,0/65,3 (c.31); 11,0/29,5/59,5 (c.33).
- **Medido (q03, média anual dos meses de cada cliente):**

  | Grupo | Clientes | % | Entrada/mês | Saída/mês | Saldo/mês |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | 1. Endividado | 493 | 49,3 | 7.454,06 | 9.190,56 | −1.736,51 |
  | 2. Vulnerável | 279 | 27,9 | 8.979,65 | 8.173,50 | 806,15 |
  | 3. Saudável | 228 | 22,8 | 9.914,23 | 7.263,36 | 2.650,86 |

- **Aviso:** as saídas incluem *Pagamento de fatura* (R$ 18,2 mi). Se os gastos no cartão também aparecem como lançamentos próprios, há dupla contagem. Isso está `NAO_VERIFICADO` e pode inflar o grupo Endividado.

### C07 · Anatomia do gasto por grupo — célula 15 · fonte `SINTETICO`

- **Consulta:** percentuais sorteados por grupo (juros 25% no Endividado, 5% no Saudável).
- **Sem equivalente medido:** a proporção de juros é um parâmetro do sorteio. Na base real, *Juros pagos* soma R$ 541 mil em 4.755 lançamentos (q02).

### C08 · Monetização por perfil — células 17, 38 · fonte `FIXO`

- **Consulta:** receita do banco (320 / 110 / 45) e `% gasto com banco` (24,5 / 12,0 / 3,5, depois 15,83 / 12,11 / 9,98) digitados ou sorteados.
- **Medido (q06):** *Empréstimos e financiamentos* é **24,57%** das saídas e *Produtos financeiros*, **19,71%**. O notebook usa 5,5% para "Banco/Taxas".
- **Conclusão:** a matriz do Passo 4 (célula 38) repete valores digitados. A taxa de **1,49% a.m.** e o **100% CDI** não saíram de nenhum RAG executado.

### C09 · Regra 50/30/20 — células 19-20 · fonte `SINTETICO`

- **Regra (mantida em `consultas.diagnostico_50_30_20`):** fixo > 53% → Alerta Fixo; variável > 33% → Oportunidade Variável; investimento < 10% → Construção de Futuro; senão Equilibrado.
- **Aviso:** o texto da recomendação fala em "poupança abaixo de 20%", mas o limiar do código é 10%.

---

## Coorte de dezembro

### C10 · Coorte negativada e evolução no ano — células 25-26, 31, 36-37 · fonte `SINTETICO`

- **Consulta:** clientes com saldo < 0 em dezembro; médias mensais de entradas e saídas da coorte ("Tesoura de Liquidez").
- **Notebook diz:** 35,1% da base. A coorte é saudável de janeiro a setembro e quebra no 4º trimestre, o que ele chama de "choque sazonal".
- **Medido (q04):** **316 de 1.000 clientes (31,6%)**. Dívida de dezembro: média R$ 2.573,41, mediana R$ 1.638,49. A coorte fica **negativa em todos os 12 meses** (saldo médio entre −430,85 em fevereiro e −2.573,41 em dezembro). Em novembro as entradas sobem para 8.297,30, provavelmente pelo 13º, mas as saídas acompanham.
- **Conclusão:** na base real o déficit é **estrutural o ano inteiro**, com piora em dezembro. A narrativa de "choque sazonal" não se sustenta.

### C11 · Matriz de essencialidade e margem de corte seguro — células 27-30 · fonte `FALLBACK` (c.27) e `REAL`-derivado (c.29)

- **Regras (mantidas em `consultas.classificar_essencialidade` e `margem_de_corte_seguro`):** casa, mercado, saúde e educação → Nível 3; restaurante, cuidados e transporte → Nível 2; o resto → Nível 1. Margem = 100% do Nível 1 + 50% do Nível 2.
- **Aviso:** na taxonomia real, *Empréstimos e financiamentos* e *Produtos financeiros* caem no Nível 1 ("supérfluo, cortar primeiro"), o que está errado para dívida contratada. A célula 29 leu um CSV real, mas sorteou os valores sobre as categorias e chegou a 1.975 de 2.000 negativados. É um artefato do sorteio.

### C12 · Score de Flexibilidade e Meta de Economia — células 31, 36 · fonte `SINTETICO`

- **Regra:** `score = (Flexível + Supérfluo) / total de saídas do mês`; `meta = dívida / 6`.
- **Defeito na célula 36:** procura as colunas `Flexivel` e `Banco`, mas a base tem `Flexivel/Delivery` e `Banco/Taxas`. As colunas são criadas zeradas e o score dá **20,0% para todos**. O "45,0%" da célula 31 é o peso fixo do sorteio (0,25 + 0,20).
- **Em `consultas.score_de_flexibilidade`:** categoria ausente é erro, com prova negativa em `tests/test_consultas_i_agora.py`. Na base real o score continua **bloqueado** até alguém decidir quais `nom_cate_macro` contam como flexível e supérfluo.

---

## Agente

### C13 · Calibração (Passo 2) e matriz de produtos (Passo 4) — células 35, 38 · fonte `FIXO`

- **Passo 2:** um dicionário com a persona "Marina, 32, autônoma" e três respostas (prioridade, risco, tom). Não há questionário executado.
- **Passo 4:** `MATRIZ_PRODUTOS` (em `consultas.py`) liga o cluster ao produto. `recomendar_produto` recusa cluster desconhecido.
