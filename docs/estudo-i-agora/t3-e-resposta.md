# T3 e faixa de resposta do agente

Segmentação comportamental **T3** (Vulnerável, Esbanjador, Livre) pelos fluxos **Inflow / Outflow / Surplus**, medida na tabela real, e a tese que sai dela: **cada segmento tem uma faixa de tom e sentimento, e a resposta do agente só sai se um guard reexecutar a própria query e confirmar os números**.

> Selo de todos os números abaixo: `batalha-time-02-lxof.hackathon_dados.extrato_sintetico` · medido em 2026-09-27T04:06 BRT (ADC) · arquivos [`estatistica_t3.json`](medicoes/2026-09-27/estatistica_t3.json) e [`guard_e2e.json`](medicoes/2026-09-27/guard_e2e.json), gerados por [`sql/medir_t3.py`](sql/medir_t3.py). Base **sintética**.

## 1. Definição (proposta, a validar pelo dono da tese)

Os termos T3/Inflow/Outflow/Surplus não existiam no código. A regra abaixo é a proposta desta revisão e mora num único lugar, `apps/context_agent_datadriven/pastas_raiz/estudos/i_agora/t3.py`. O SQL recebe dali o mapa de grupos (`{{GRUPOS}}`) e o limiar (`{{LIMIAR_SURPLUS}}`).

| Fluxo | Regra (média mensal por cliente) |
| --- | --- |
| Inflow | soma de `vlr` com `tipo = 'E'` |
| Outflow | soma de `vlr` com `tipo = 'S'` |
| Surplus | Inflow − Outflow; taxa = Surplus ÷ Inflow |

| Segmento | Condição |
| --- | --- |
| **Livre** | taxa de Surplus ≥ 15% |
| **Esbanjador** | taxa < 15%, mas (Surplus + discricionário) ÷ Inflow ≥ 15%: cortar só o discricionário devolve o cliente a Livre |
| **Vulnerável** | o resto: nem zerando o discricionário chega a 15% (ou Inflow ≤ 0) |

- **Janela:** meses completos antes do mês do corte da tese (22/12/2025), ou seja, jan–nov/2025. Os 1.000 clientes têm os 11 meses.
- **Grupos de saída:** as 21 macros medidas em q06 foram mapeadas em 4 grupos (`t3.MAPA_GRUPOS`). O mapa cobre 100% das saídas (`saidas_sem_grupo = 0`), e um teste reprova macro nova.

| Grupo | Macros |
| --- | --- |
| essencial | Casa, Mercado, Educacao, Transporte publico, Posto de combustivel, Veiculos |
| compromisso_financeiro | Emprestimos e financiamentos, Produtos financeiros, Boletos diversos |
| discricionario | Lazer, Lojas e sites, Viagens, Restaurantes, Delivery, Assinaturas, Cuidados pessoais, Transporte por app, Pets |
| nao_classificado | Transferencias diversas, Outros gastos, Saque |

## 2. Análise estatística aplicada

### 2.1 Participação (IC 95% por bootstrap de clientes, 2.000 reamostras, semente fixa)

| Segmento | n | % | IC 95% |
| --- | ---: | ---: | --- |
| Vulnerável | 453 | 45,3 | 42,1 – 48,4 |
| Esbanjador | 286 | 28,6 | 25,8 – 31,5 |
| Livre | 261 | 26,1 | 23,4 – 28,8 |

Os intervalos não se sobrepõem entre Vulnerável e os outros dois. A regra antiga de q03 (49,3 / 27,9 / 22,8) usa outra definição (saldo do ano), então os números **não são comparáveis um a um**.

### 2.2 Perfil de cada segmento (medianas; % do Inflow)

| Métrica | Vulnerável | Esbanjador | Livre |
| --- | ---: | ---: | ---: |
| Inflow mensal | R$ 8.084,26 | R$ 8.471,58 | R$ 10.764,95 |
| Outflow mensal | R$ 9.515,92 | R$ 8.103,19 | R$ 7.723,62 |
| Taxa de Surplus (IC 95% da mediana) | −21,0% (−23,3 a −18,9) | 5,8% (4,7 a 6,4) | 23,4% (22,3 a 24,5) |
| Essencial | 36,4% | 28,1% | 22,6% |
| Compromisso financeiro | 57,2% | 42,6% | 35,6% |
| Discricionário | 19,0% | 18,0% | 10,9% |
| Volatilidade do Inflow (coeficiente de variação) | 14,8% | 15,7% | 15,7% |

As descritivas completas (média, desvio, p10–p90) estão em `estatistica_t3.json › por_segmento`.

### 2.3 Sensibilidade do limiar

| Limiar | Vulnerável | Esbanjador | Livre | Clientes que mudam de segmento vs 15% |
| --- | ---: | ---: | ---: | ---: |
| 10% | 37,0% | 29,3% | 33,7% | 159 |
| **15%** | 45,3% | 28,6% | 26,1% | 0 |
| 20% | 56,4% | 25,7% | 17,9% | 193 |

Mudar o limiar em 5 pontos move entre 16% e 19% da base, então o limiar **é uma decisão de negócio e não um detalhe**. O Esbanjador é o segmento mais estável (25,7–29,3%). A matriz de migração está em `sensibilidade_do_limiar`.

### 2.4 O que separa os segmentos (Spearman, p-valor por 5.000 permutações)

| Par | ρ | p |
| --- | ---: | ---: |
| Compromisso ÷ Inflow × taxa de Surplus | −0,69 | < 0,001 (menor p possível com 5.000 permutações) |
| Discricionário ÷ Inflow × taxa de Surplus | −0,65 | < 0,001 |
| Volatilidade do Inflow × taxa de Surplus | −0,04 | 0,24 |

Leitura, com os limites:

- Nesta base **o que separa os segmentos é a composição da saída** (compromisso e discricionário), não a instabilidade da renda: o coeficiente de variação é o mesmo nos três e não correlaciona. Por isso o foco de cada perfil de resposta (§3) é um grupo de saída.
- As duas correlações fortes são **em parte mecânicas**: compromisso e discricionário são pedaços do Outflow, que entra na taxa. Elas mostram onde está o peso, não uma causa.
- `NAO_VERIFICADO`: "Pagamento de fatura" (R$ 18,2 mi, dentro de Produtos financeiros) pode contar em dobro compras que já aparecem nas outras macros. Se contar, o compromisso (57% do Inflow no Vulnerável) e o próprio Outflow estão inflados, e parte dos Vulneráveis mudaria de segmento. É a primeira coisa a confirmar com quem gerou a base.

## 3. Tese de resposta: uma faixa por segmento

Fonte única: `t3.PERFIS_DE_RESPOSTA`. O guard mede o texto contra esta tabela.

| Segmento | Tom | Sentimento léxico | `!` máx | Foco | Proibidos | Precisa de um de |
| --- | --- | --- | ---: | --- | --- | --- |
| Vulnerável | acolhedor e protetor | 0,0 a 0,5 | 0 | compromisso: renegociar antes de cortar essencial | novo empréstimo, novo crédito, aproveite, urgente, garantido, sem risco | vamos, juntos, passo, organizar, proteger |
| Esbanjador | direto e encorajador | −0,2 a 0,4 | 1 | discricionário: nomear a categoria e o valor | irresponsável, descontrole, culpa, garantido, sem risco | reduzir, cortar, ajustar, meta, limite |
| Livre | consultivo | 0,2 a 0,7 | 1 | excedente: reserva e investimento, sem promessa de retorno | rentabilidade garantida, sem risco, garantido, lucro certo | reserva, investir, aplicar, planejar, objetivo |

- **Sentimento léxico:** (positivas − negativas) ÷ (positivas + negativas), com as listas de `guard.py`. É contagem de palavras, **não leitura semântica**. Texto sem nenhuma palavra do léxico sai `NAO_MEDIDO`, nunca zero.
- **As faixas são hipótese de desenho.** Nenhuma resposta real do agente foi medida contra elas ainda.
- **Limite medido:** o texto eufórico de teste ("incrível e fantástico") teve escore 0,14 no Esbanjador, dentro da faixa. Quem o reprovou foram os `!` e o termo proibido "sem risco". O escore não pega euforia sozinho.

## 4. Visões por assunto (o que o agente pode consultar)

Cada tópico é um SQL em `apps/context_agent_datadriven/pastas_raiz/estudos/i_agora/sql/` precedido de `_base_cliente.sql`. Os parâmetros são `@id_usuario` e `@data_corte`, mais `@categoria` na visão de categoria. Cada visão devolve **uma linha**.

| Tópico | Arquivo | Campos |
| --- | --- | --- |
| `perfil_t3` | `visao_perfil_t3.sql` | inflow/outflow/surplus mensais, taxa_surplus_pct, 4 grupos mensais, meses, saidas_sem_grupo, segmento_t3 |
| `categoria` | `visao_categoria.sql` | categoria, grupo, lancamentos, total, media_mensal, pct_do_outflow, meses |
| `renda` | `visao_renda.sql` | salario_clt_total, recebimentos_diversos_total, outras_entradas_total, inflow_total, inflow_mensal, volatilidade_inflow_pct |
| `dividas` | `visao_dividas.sql` | compromisso_total/mensal, fatura_total, emprestimos_financiamentos_total, juros_pagos_total, multas, lancamentos_parcelados, pct_inflow_comprometido |
| `recorrencias` | `visao_recorrencias.sql` | lancamentos_assinaturas, assinaturas_total/mensal, servicos_distintos |
| `discricionario` | `visao_discricionario.sql` | maior_categoria_discricionaria, maior_categoria_total, discricionario_mensal, categorias_discricionarias |

Como `visoes.py` trata cada pedido:

- `rotear(pergunta)` escolhe o tópico. Uma macro citada pelo nome vence, e depois conta a palavra-chave.
- Pergunta sem tópico, categoria fora do mapa ou tópico desconhecido levantam `ForaDoCatalogo`: sem visão, o agente não cita número.
- `ExecutorBigQuery` faz um dry-run antes e não roda acima de 100 MB. Uma visão mede cerca de 33 MB.

## 5. Guard de inclusão do dado

**Fluxo:** o agente consulta a visão, escreve e envia `{dados, texto, segmento_t3}` ([`envio-agente.schema.json`](schemas/envio-agente.schema.json)). Depois espera o veredito ([`veredito-guard.schema.json`](schemas/veredito-guard.schema.json)).

`guard.verificar_envio` reexecuta **o mesmo SQL** (o hash `sql_sha256` vai no retorno) e confere:

| Checagem | Reprova quando |
| --- | --- |
| `dados.<campo>` | o campo não existe na linha, ou o valor difere após normalizar (número com 2 casas; "R$ 1.638,49" e "52,24%" viram número; rótulo sem acento e sem caixa) |
| `numero <bruto>` | um R$ ou % do texto não tem fonte nas linhas consultadas, na precisão escrita ("R$ 4.141" aceita 4.141,27; "R$ 4.150" não) |
| `segmento` | o segmento declarado difere do `segmento_t3` do SQL |
| `mapa_grupos` | há saída sem grupo no mapa |
| `tom.*`, `sentimento` | fora da faixa do segmento **calculado** (§3) |

**Veredito:** qualquer REPROVADO reprova. Senão, qualquer NAO_MEDIDO dá NAO_MEDIDO. Senão, APROVADO.

**Prova no BigQuery real** (`guard_e2e.json`). Para cada segmento foi usado o cliente de taxa mediana:

| Segmento | SQL × Python | Envio correto | Dado +R$ 100 | Texto eufórico |
| --- | --- | --- | --- | --- |
| Vulnerável | Vulnerável = Vulnerável | APROVADO | REPROVADO (`dados.compromisso_mensal`) | REPROVADO (`!`, "aproveite") |
| Esbanjador | Esbanjador = Esbanjador | APROVADO | REPROVADO (`dados.discricionario_mensal`) | REPROVADO (`!`, "sem risco") |
| Livre | Livre = Livre | APROVADO | REPROVADO (`dados.surplus_mensal`) | REPROVADO (`!`, "sem risco") |

Os 9 envios e retornos passam nos dois schemas. As provas negativas dos schemas (categoria fora do tópico, `dados` vazio, veredito inválido) reprovam.

**O que o guard não cobre:**

- Números sem R$ ou % ("3 meses") não são conferidos.
- O roteamento é por palavra-chave.
- Nada disso está ligado ao `primeira_chamada.py` ainda: o agente em produção não chama o guard.

## Reproduzir

```powershell
..\.venv\Scripts\python.exe docs\estudo-i-agora\sql\medir_t3.py      # estatistica_t3.json e guard_e2e.json
$env:PYTHONPATH = '.'; ..\.venv\Scripts\python.exe -m unittest tests.test_t3_guard_i_agora -v
```
