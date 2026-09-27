# Bateria de valor — 2026-09-27

Fonte: `datasets/bateria-valor-2026-09-27.jsonl` (30 exemplos + 3 reexecuções, append-only). Dados: BigQuery `batalha-time-02-lxof.hackathon_dados.extrato_sintetico` (ADC, data de corte 2025-12-22; jobs por linha em `selo`). Gemini ao vivo em processo (`interacao.interagir`), no máximo 1 chamada de redação por exemplo, guard de entrada pelo modelo desligado (quota gratuita de 20 pedidos/dia por modelo). Gerado por `scratchpad/bateria/bateria.py` e `resumo.py`.

## Chamadas ao Gemini

- MEDIDO (chamou e avaliou): 16
- SEM_MODELO (resposta fixa fora do contexto): 9 (6 fora de contexto + 3 que o classificador tirou do domínio por engano, ver abaixo)
- NAO_MEDIDO: 5 (2 com 429 GenerateRequestsPerDay e 3 não chamados porque os dois modelos já davam 429). Esses 5 NÃO contam como aprovados: faltaram por quota.
- gemini-flash-latest: 429 em toda chamada do dia; gemini-3.5-flash-lite: 16 chamadas até dar 429.

## Acerto do cenário (determinístico) por cenário esperado

| cenário | exemplos | acerto na 1ª execução | após conserto do classificador (reexecução) | Gemini aprovado na 1ª tentativa |
|---|---|---|---|---|
| inclinacao_gasto | 10 | 8/10 (80%) | 10/10 (100%) | 5/5 (100%) |
| consolidacao_divida | 8 | 7/8 (88%) | 8/8 (100%) | 5/5 (100%) |
| financeiro_geral | 6 | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) |
| fora_do_contexto | 6 | 6/6 (100%) | 6/6 (100%) | sem Gemini |

**Consolidação NÃO deu 100% na primeira execução** (7/8): o caso que falhou foi o classificador de domínio, não o gatilho de dívida. Casos falhados:

- `bv-05` usuário 571, "como saio do vermelho?": esperado `consolidacao_divida`, obtido `fora_do_contexto` (faltava "vermelho"/"exagerando"/"categoria" no léxico financeiro). Reexecução `bv-05r` após o conserto: `consolidacao_divida` (sem Gemini, quota esgotada; texto = esqueleto do servidor).
- `bv-10` usuário 125, "estou exagerando em alguma categoria?": esperado `inclinacao_gasto`, obtido `fora_do_contexto` (faltava "vermelho"/"exagerando"/"categoria" no léxico financeiro). Reexecução `bv-10r` após o conserto: `inclinacao_gasto` (sem Gemini, quota esgotada; texto = esqueleto do servidor).
- `bv-22` usuário 317, "estou exagerando em alguma categoria?": esperado `inclinacao_gasto`, obtido `fora_do_contexto` (faltava "vermelho"/"exagerando"/"categoria" no léxico financeiro). Reexecução `bv-22r` após o conserto: `inclinacao_gasto` (sem Gemini, quota esgotada; texto = esqueleto do servidor).

Com dívida relevante medida e a pergunta no domínio, o cenário disparou em 100% dos casos (7/7 na 1ª execução + 1/1 na reexecução), e o teste `Cenarios.test_consolidacao_dispara_em_100_por_cento_com_divida_medida` prova-o sem rede (10 execuções, 10/10).

## Latência (só chamadas MEDIDAS do Gemini)

p50 1250 ms · p95 1566 ms · n=16 (latência do provedor; o tempo total inclui BigQuery).

## Reprovações por guard

- nas tentativas do modelo: nenhuma (16/16 aprovadas na 1ª tentativa)
- no texto final servido: nenhuma

## Exemplos literais

- **inclinacao_gasto** (`bv-02`, usuário 906, T3 Esbanjador, mês FALTOU, modelo gemini-3.5-flash-lite, 1250 ms) — pergunta "onde estou gastando mais?":  
  > Nesses últimos tempos tenho percebido uma leve inclinação a você gastar um pouco mais com Mercado: de setembro de 2025 a novembro de 2025 foram R$ 241,88 por mês, contra R$ 142,83 em média de janeiro de 2025 a novembro de 2025. Talvez valha gastar um pouco menos com Mercado.
- **consolidacao_divida** (`bv-09`, usuário 50, T3 Vulnerável, mês SOBROU, modelo gemini-3.5-flash-lite, 1266 ms) — pergunta "minhas parcelas estão pesando, e agora?":  
  > Olá Arthur, entendo que as parcelas estejam pesando e vamos organizar isso juntos com calma. Pelos seus números, de janeiro de 2025 a novembro de 2025 saíram em média R$ 3.752,55 por mês com empréstimos e juros, 32,3% da sua entrada média. Em novembro de 2025, sobrou R$ 3.166,89, com entradas de R$ 14.321,50 e saídas de R$ 11.154,61, e podemos usar essa sobra para colocar seus compromissos em ordem. Para isso, o caminho é conversar com um especialista do banco: ele avalia com você, numa negociação, a consolidação das suas dívidas, e as condições só existem depois dessa análise. Quer que eu encaminhe você para esse atendimento humano?
- **fora_do_contexto** (`bv-04`, usuário 707, T3 NAO_MEDIDO, mês NAO_MEDIDO, modelo nenhum, - ms) — pergunta "qual a capital da França?":  
  > Não faço ideia, sabia? Aí é que eu não sei.
