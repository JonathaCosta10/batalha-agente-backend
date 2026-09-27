# Decisões D-1 a D-19 e a lógica aplicada (2026-09-27)

Escrito em **2026-09-27 entre 09:30 e 09:38 BRT**, pelo relógio do Windows. O dono aceitou às **09:28 BRT** todas as
recomendações das decisões D-1 a D-19 ([backlog.md, "Decisões para fechar a entrega"](backlog.md#decisões-para-fechar-a-entrega-levantadas-em-2026-09-27-0920-brt)).
Às **09:31 BRT** ele respondeu mais duas coisas, registradas aqui: o repositório oficial (D-7) e a espera pelo OK do
Henrique para o Cloud Run (D-8).

Este documento **não muda código**. Ele registra, para cada decisão, o porquê, onde a decisão vive no código, qual
teste a prova e em que estado ela está. Depois explica a lógica de `metricas_fluxo.py`, as duas regras T3 que
convivem, o diagnóstico que pode ser publicado e, por último, a publicação no Cloud Run, que é a etapa final.

Fontes: [backlog.md](backlog.md), [rota-integrada-batalha-agentes-backend.md](rota-integrada-batalha-agentes-backend.md),
[`q_spec_diagnostico.json`](estudo-i-agora/medicoes/2026-09-27/q_spec_diagnostico.json) e
[relatorio-migracao-politica-2026-09-27.md §7-A](relatorio-migracao-politica-2026-09-27.md).

## Selos usados

| Número | Valor | Fonte | Data |
| --- | --- | --- | --- |
| T3 de produção (n = 1.000) | Vulnerável 45,3 % · Esbanjador 28,6 % · Livre 26,1 % | [t3-e-resposta.md](estudo-i-agora/t3-e-resposta.md) (`estatistica_t3.json`) | medido 2026-09-27T04:06 BRT |
| T3 da especificação, média jan–nov (n = 1.000) | Vulnerável 84,1 % · Esbanjador 2,3 % · Livre 5,2 % · sem segmento 8,4 % | `q_spec_diagnostico.json`, chave `t3_janov_cheque=saldo_apos_negativo` (job `2fed39aa`) | medido 2026-09-27T09:17 BRT |
| Crítico em dezembro inteiro (n = 1.000) | déficit 31,6 % (316) · margem 0–15 % 18,1 % (181) · crítico 49,7 % (497) | mesmo arquivo, `critico_dez` | 09:17 BRT |
| Crítico até 22/12 (n = 1.000) | déficit 13,8 % · margem 0–15 % 10,3 % · crítico 24,1 % | mesmo arquivo, `critico_dez22` | 09:17 BRT |
| Crítico na média jan–nov (n = 1.000) | déficit 50,3 % · margem 0–15 % 23,6 % · crítico 73,9 % | mesmo arquivo, `critico_janov` | 09:17 BRT |
| Gatilhos do Vulnerável (n = 1.000, 12 meses) | juros pagos 695 · saldo negativo 327 · micro "Cheque" 73 | mesmo arquivo, `gatilhos_vulneravel_janov` | 09:17 BRT |
| Suíte completa | 470 OK, com 23 expectedFailure | [backlog.md:193](backlog.md) | 09:26 BRT (não rodada por mim) |
| Suíte completa (depois do Cloud Run) | 517 testes: 1 FAIL, 21 expectedFailure, 1 unexpected success (f7 em curso; ver §5.3 item 2) | `unittest discover -s tests` | rodada 09:53–09:54 BRT |
| Suítes da especificação | 105 testes: 85 OK e 20 expectedFailure | [backlog.md:193](backlog.md) | 09:26 BRT |
| Recall do detector de extremos | 3/12 → 7/12 | relatório §7-A | ~09:15 BRT |
| Conferência dos exemplos desta página | 43 de 43 conferências OK | script [`conferir_exemplos_metricas_fluxo.py`](estudo-i-agora/medicoes/2026-09-27/conferir_exemplos_metricas_fluxo.py) | rodado 09:32 BRT |

---

## 1. As 19 decisões

Estados: **APLICADO** (código e teste presentes) · **EM CURSO** (com quem) · **SEM MUDANÇA DE CÓDIGO** (a decisão
confirma o que já existe ou é só publicação) · **BLOQUEADO** (de quem, e do que se espera).

**Atualizado às 09:50 BRT** (conferido no disco). APLICADO, com arquivo:linha e teste: D-3 (410 e `archive/`), I9
(chave no cabeçalho), D-4 no lado do `perfil_usuario`, D-5 e D-6. A f7 está fazendo, aprovado às **09:41**: I4 no
`ConversationService`, I5 (D-14) e D9 (D-15). A I2 já foi feita pela f7: `MODELOS_GOOGLE` começa por
`gemini-3.5-flash-lite` (`desafio_itau/modelos_llm.py:22`). D-7: escolhido o clone publicado; a cópia é o último
passo antes do deploy. A primeira conferência deste quadro foi às 09:33 BRT.

**Aviso sobre D-9 a D-16.** O backlog lista essas oito decisões sem escrever uma recomendação explícita. Aqui, a
"recomendação aceita" é o valor que o código já usa (a constante em `metricas_fluxo.py` ou a regra de produção).
Se o dono quis dizer outra coisa, a linha precisa ser corrigida.

| # | Decisão | Recomendação aceita | Lógica: por que, constatação e selo | Onde vive no código | Teste que prova | Estado |
| --- | --- | --- | --- | --- | --- | --- |
| D-1 | Regra T3 oficial | Manter a regra de produção. A da especificação fica como referência testada | Com a especificação, 84,1 % da base recebe o tom de Vulnerável, e o tom deixa de separar as pessoas. Selo: `q_spec_diagnostico.json`, 09:17 BRT. A produção dá 45,3/28,6/26,1 % (04:06 BRT) | `pastas_raiz/estudos/i_agora/t3.py:96-108`; `sql/visao_perfil_t3.sql:25-30`; referência em `services/metricas_fluxo.py:453-508` | `tests/test_spec_t3_regras.py:148-190` (`DivergenciaComT3Atual`, 4 expectedFailure que registram a diferença) | SEM MUDANÇA DE CÓDIGO |
| D-2 | Diagnóstico populacional a publicar | Publicar o medido, com selo | O N=316 é a coorte com déficit em dezembro inteiro. Nessa coorte o déficit é 100 % por definição, então não pode ser 28,8 %. Nenhum corte reproduz 28,8, 19,6 ou 48,4 % (`varredura_28_8_e_19_6.casamentos_exatos = []`, 09:17 BRT). Ver §4 | Não há código: é publicação. Consulta em `docs/estudo-i-agora/medicoes/2026-09-27/q_spec_diagnostico_por_cliente.sql` | NAO_MEDIDO: não há teste; a prova é o JSON selado | SEM MUDANÇA DE CÓDIGO (esta página publica os números) |
| D-3 | Rota do front | Só `conversas/interacao/`; `enviar-mensagem/` vai para `archive/` | I1: com o usuário 928, a rota chamou a pessoa de "Eduarda" (cliente demo). I9: `cliente.py` punha a chave do Gemini na URL | `apps/context_agent_datadriven/views.py:67-78` (`EnviarMensagemHarnessAPI` responde 410 Gone com JSON apontando `conversas/interacao/`), montada em `urls.py:18`. Código antigo em `archive/2026-09-27/` (views, models, `agente_service.py`, testes), com linhas em `archive/INDICE.md`. **I9:** chave no cabeçalho `x-goog-api-key` (`agentes/LLM_Models/google/cliente.py:50-55`) | `tests/test_d3_rota_unica.py:65` (410 para todo método), `:93` (URL sem `key=`), `:102` e `:112` (provas negativas, varredura AST) | **APLICADO** (conferido 09:49) |
| D-4 | Duração da sessão | 4 h em tudo, com a sessão gravada (I4) | D3 da rota integrada: sessão 4 h e conversa 30 min. O `runserver` recarrega e apagava as sessões em memória | Lado do `perfil_usuario`: model `SessaoPerfilUsuario` (`apps/context_agent_datadriven/models.py:64`), migração `0002_sessao_perfil_usuario.py`, TTL 4 h lido em `services/perfil_usuario.py:106`. Lado do `ConversationService`: com a f7 (`apps/conversas/persistencia.py`, em curso às 09:50) | `tests/test_d4_sessao_persistente.py:74` (sobrevive ao reinício), `:82` (prova negativa: armazém em memória perde), `:93` (TTL 4 h), `:111` (expirada dá 404 sem chamar o modelo) | **APLICADO** no `perfil_usuario`; **EM CURSO com a f7** no `ConversationService` (I4, aprovado às 09:41) |
| D-5 | CSRF nas portas 3000 e 3001 | Aceitar as duas | D12: o contrato manda usar o Vite na 3001, e o CSRF só aceitava a 3000 | `desafio_itau/settings.py` (`FRONT_ORIGENS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`; em produção, origens extras de CSRF em `DJANGO_CSRF_TRUSTED_ORIGINS`) | `tests/test_d5_origens_front.py:36-51` (prova negativa `:51`: porta 3002 e outro host recusados); `tests/test_cloud_run_prontidao.py` (`test_csrf_extra_do_ambiente_soma_as_origens_da_d5`) | **APLICADO** |
| D-6 | Lista de extremos (item 5 da f7) | Aprovar, com prova negativa | I8: pegava 3 de 12 frases de crise. Medido 7/12 (58,3 %) às **09:40 BRT**, depois do léxico novo da f7. "Sumir com a dívida" não dispara | `apps/conversas/extremos.py` (lista da f7); piso em `tests/test_corpus_intencao_gemini.py:25-29` (extremo 25 → **58 %**) | `tests/test_corpus_intencao_gemini.py:75-77` (pisos) e `:84` (prova negativa: classificador ruim fica abaixo do piso); `tests/test_extremos_recall.py` | **APLICADO** (piso de 58 %; a meta da I8, ≥ 10/12 e 83 %, segue aberta) |
| D-7 | Repositório oficial | Escolher um e copiar o que só existe localmente | I7: esta pasta não tem git. **Resposta do dono às 09:31:** o oficial é o clone publicado `old/desafio-itau-batalha-de-agentes-time2`. O que só existe aqui vai para lá, com commit local. Push só com autorização explícita do dono no momento | Lista do que copiar: §5.3. Entram também os arquivos do Cloud Run criados às 09:47 (`Dockerfile`, `.dockerignore`, `desafio_itau/saude.py`, `tests/test_cloud_run_prontidao.py`) | NAO_MEDIDO: a prova será `git status` limpo no clone depois da cópia | **ESCOLHIDO** (o clone publicado). A cópia é o **último passo antes do deploy**, depois de a f7 fechar I4/I5/D9 |
| D-8 | Cloud Run | Só depois de D-3, D-4, D-5 e D-7 | Regra do front. **Resposta do dono às 09:31:** é a etapa final e espera o OK do Henrique | Código pronto para o Cloud Run (settings do ambiente, `/healthz`, `Dockerfile`): ver §5 | `tests/test_cloud_run_prontidao.py` (10 testes); teste de fumaça da §5.5 NÃO EXECUTADO | BLOQUEADO: espera a f7 (I4 no `ConversationService`), a cópia da D-7 e o **OK do Henrique**. O deploy não é deste agente |
| D-9 | "Juros pagos" como gatilho de Vulnerável | Não é gatilho. Continua contando como má dívida (dívida cara do Livre) | Atinge 695 de 1.000 clientes; como gatilho OU, leva 97,8 % (309/316) da coorte N=316 a Vulnerável. O gatilho deixaria de discriminar. Selo: `q_spec_diagnostico.json`, 09:17 | `metricas_fluxo.py:133-138` (`JUROS_PAGOS_E_CREDITO_EMERGENCIAL = False`) | `test_spec_t3_regras.py:62`; `test_spec_dividas_longitudinal.py:40` | SEM MUDANÇA DE CÓDIGO |
| D-10 | Proxy de cheque especial | `saldo_apos < 0` em algum lançamento do mês. O micro "Cheque" fica fora | A base não tem categoria de cheque especial. O saldo negativo atinge 327 de 1.000; "Cheque" (73) é pagamento em cheque. Selo: 09:17 | `metricas_fluxo.py:111-117`, `:373-374` | `test_spec_dividas_longitudinal.py:56`, `:63`, `:70` | SEM MUDANÇA DE CÓDIGO |
| D-11 | Quem fica sem segmento | `SEM_SEGMENTO`, sem forçar o perfil mais próximo | As condições da especificação não cobrem todos os casos: 8,4 % da base fica de fora (09:17) | `metricas_fluxo.py:35-38`, `:507-508` | `test_spec_t3_regras.py:127` (`test_existe_cliente_sem_segmento`) | SEM MUDANÇA DE CÓDIGO (só na regra de referência; a produção sempre classifica) |
| D-12 | Fórmula dos scores | Margem linear até 100 %, sem corte em 15 % | Com `clip(margem/0,15)`, a média deu exatamente 100,0 no Esbanjador e no Livre (09:17). O 100,0 é saturação da conta, não um cliente perfeito | `metricas_fluxo.py:159-168`, `:513-516` | `test_spec_scores.py:119` (20 % ≠ 60 %) e `:128` (prova da saturação) | SEM MUDANÇA DE CÓDIGO (os scores da especificação não estão ligados à conversa) |
| D-13 | Janela de referência | Média jan–nov/2025, como a produção | Dezembro só vai até o dia 22 (data de corte), e é mês sazonal. A regra do dono das 06:22 fixa a média jan–nov (relatório §7-A, linha "Dezembro completo × média jan–nov") | `t3.py:8-9`; `apps/conversas/interacao_dados.py:156-157` | `test_spec_dividas_longitudinal.py:129` (expectedFailure: o T3 não inclui dezembro) | SEM MUDANÇA DE CÓDIGO |
| D-14 | Memória no turno livre (I5) | Guardar os 4 últimos turnos por `sessao_id`, como dado não confiável | "E em fevereiro?" perde o referente, porque cada POST de `interacao/` é isolado | `apps/conversas/interacao.py` (f7, em curso) | `tests/test_fechamento_i4_i5_d15.py` (f7, criado às 09:49); `tests/test_quatro_rotas.py` (I5 como expectedFailure) | **EM CURSO com a f7** (I5, aprovado às 09:41) |
| D-15 | Contrato de `interacao/` e divergências D5–D9 | Proposta da f7: usar `contrato.estado` como schema fixo de `interacao/` | `interacao/` não devolvia `contrato`; erros 4xx saíam com `schema_version "1.0"` | `apps/conversas/interacao.py`; `views_interacao.py` (f7, em curso) | `tests/test_fechamento_i4_i5_d15.py` (f7) | **EM CURSO com a f7** (D9, aprovado às 09:41) |
| D-16 | Open Finance | Fica como função testada, fora da produção. "Zerar o crédito" = penalidade máxima | Não há dado de Open Finance na base. A leitura oposta (penalidade 0) premiaria o atraso | `metricas_fluxo.py:170-173`, `:562-580` | `test_spec_open_finance.py` (8 OK; `:70` e `:75` expectedFailure: o T3 e os fluxos não conhecem o segmento) | SEM MUDANÇA DE CÓDIGO |
| D-17 | Livre orientado a investimento? | Manter a proibição na entrega (BCB RC 8/2023) | A especificação pede investimento; o prompt e o guard proíbem recomendar produto | `apps/conversas/prompts/interacao.liquid:18`; `apps/conversas/interacao_avaliacao.py:284-286` (`PRODUTOS`) | `test_spec_tom_por_perfil.py:146` e `:152` (expectedFailure que registram a divergência) | SEM MUDANÇA DE CÓDIGO |
| D-18 | Tom do Esbanjador | Direto, falando de trade-offs, sem provocar | "Provocativo" arrisca julgamento; o léxico já proíbe "irresponsável" e "culpa" | `t3.py:122-129` (`"tom": "direto e encorajador"`) | `test_spec_tom_por_perfil.py:122-134` (expectedFailure de "provocativo") | SEM MUDANÇA DE CÓDIGO |
| D-19 | Separar má dívida de boa dívida | Separar | A produção põe todo "Emprestimos e financiamentos" em compromisso e soma financiamento de imóvel como empréstimo | Separação só existe em `metricas_fluxo.py:345-359`. Produção: `t3.py:46-47`, `interacao_dados.py:94` | `test_spec_dividas_longitudinal.py:112` e `:122` (expectedFailure) | BLOQUEADO: nenhum agente tem a tarefa. Espera o dono nomear quem aplica em `interacao_dados.py:94` |

---

## 2. Lógica aplicada em `metricas_fluxo.py`

Arquivo: [`apps/context_agent_datadriven/services/metricas_fluxo.py`](../apps/context_agent_datadriven/services/metricas_fluxo.py).
É a especificação de produto do dono escrita como código puro: sem Django, sem BigQuery e sem modelo. **Ela não
substitui o T3 de produção** (D-1). Existe para que a especificação seja executável e testada.

Unidades: valores em R$ como `Decimal` (um `float` passa por `str()` para não herdar erro binário); margem em
percentual (15 = 15 %); razões em fração (0,85); mês como inteiro AAAAMM.

Todos os exemplos abaixo foram calculados à mão a partir das fórmulas e depois conferidos rodando as funções
(43 conferências, 43 OK, 09:32 BRT, script citado nos selos). O módulo não foi editado.

### 2.1 Inflow, Outflow, Surplus e margem (`metricas_mes`, `margem_pct`, linhas 318-402)

- **Inflow** = soma do valor absoluto dos lançamentos de entrada do cliente no mês (tipo `E`, `V` ou `True`).
- **Outflow** = soma do valor absoluto das saídas (tipo `S`, `F` ou `False`). Tipo desconhecido é erro, e não
  vira saída por omissão (`eh_entrada`, linha 275).
- **Surplus** = Inflow − Outflow.
- **Margem** = Surplus ÷ Inflow × 100. Com Inflow = 0, a margem é `None` (NAO_MEDIDO), nunca 0 nem −100 %
  (linha 321).
- Na mesma passada, cada saída é separada em **fixo** (aluguel, condomínio, IPTU, luz, água), **variável** (Lazer,
  Lojas e sites, Restaurantes), **parcelas** (as quatro subcategorias de financiamento) e **má dívida**.

Exemplo, cliente `u1` em 01/2025:

| Lançamento | Valor |
| --- | --- |
| Entrada, Salário CLT | 5.000 |
| Saída, Casa / Pagamento de aluguel | 1.500 |
| Saída, Lazer | 800 |
| Saída, Produtos financeiros / Juros pagos | 50 |
| Saída, Financiamento de imóvel (valor −1.000 na base) | 1.000 |

À mão: Inflow = 5.000. Outflow = 1.500 + 800 + 50 + 1.000 = 3.350. Surplus = 1.650. Margem = 1.650 ÷ 5.000 × 100 =
**33 %**. Fixo 1.500, variável 800, parcelas 1.000, má dívida 50 (juros pagos), crédito emergencial 0.
Fronteira: Inflow 1.000 e Outflow 850 dão margem **exatamente 15 %**. Inflow 0 dá **None**. Tudo conferido.

### 2.2 Classificação de dívida (`classificar_divida`, linhas 329-359)

| Classe | Quando | Crédito emergencial? |
| --- | --- | --- |
| Má dívida | micro com "cheque especial" ou "rotativo"; tarifas (`Outras tarifas financeiras`, `Anuidade e pacote de servico`); `Multa por atraso`; `Juros pagos` | só cheque especial e juros rotativos |
| Boa dívida | `Financiamento de imovel` com parcela ≤ **30 %** do Inflow do mês | não |
| Financiamento incompatível | a mesma parcela acima de 30 % (a especificação não diz se é boa ou má) | não |
| NAO_MEDIDO | financiamento sem parcela ou sem Inflow | não |
| Fora da especificação | o resto, incluindo o micro "Cheque" de Outros gastos (pagamento em cheque) | não |

Exemplos: parcela 1.500 com Inflow 5.000 → 1.500 ÷ 5.000 = 0,30 ≤ 0,30 → **boa dívida**. Parcela 1.501 → 0,3002 →
**incompatível**. `Juros pagos` → má dívida, **não** emergencial. "Cheque especial" → má dívida emergencial.
"Cheque" → fora da especificação. Tudo conferido.

### 2.3 Avaliação longitudinal (`avaliar_longitudinal`, linhas 407-427)

Déficit é Surplus **< 0** (zero não é déficit). Ordem das regras:

1. Nenhum mês com déficit → `SEM_DEFICIT`.
2. Três meses ou mais com déficit → `INSUSTENTAVEL`, mesmo que um deles seja dezembro.
3. Todos os déficits em dezembro → `SAZONAL`.
4. O resto (um ou dois meses fora de dezembro) → `PONTUAL`.

O campo `completo` diz se há os 12 meses de algum ano.

Exemplos com 12 meses de Surplus +100: só dezembro −100 → **SAZONAL**, completo. Março e dezembro −1 → **PONTUAL**.
Outubro, novembro e dezembro −1 → **INSUSTENTAVEL**. Junho com Surplus 0 → **SEM_DEFICIT**. Só novembro (−5) e
dezembro (+10) → **PONTUAL**, incompleto. Tudo conferido.

### 2.4 Regra T3 da especificação (`classificar_t3_spec`, linhas 453-508)

A regra soma os meses da janela e calcula Inflow, Outflow, Surplus e margem do total. Depois testa três
candidatos:

- **Vulnerável** se valer qualquer uma: Surplus < 0; margem < 15 %; uso de cheque especial (proxy) ou crédito
  emergencial em um dos **3 meses mais recentes**.
- **Esbanjador** se valerem todas: 0,70 ≤ Outflow/Inflow ≤ 0,85 (ponta de cima fechada); variável ÷ Outflow ≥
  **0,1593** (mediana medida às 09:17); nenhum mês com cheque especial; Inflow médio alto. O limiar do Inflow
  médio não existe na especificação: o critério fica como satisfeito e a pendência `inflow_medio_alto_nao_avaliado`
  sai na resposta.
- **Livre** se valerem todas: margem ≥ 15 %; pelo menos **3 meses quaisquer** com margem ≥ 15 %; nenhum mês com
  crédito emergencial; má dívida ÷ Inflow **< 10 %**.

**Precedência:** Vulnerável > Esbanjador > Livre > `SEM_SEGMENTO` (o risco manda). Sem movimento na janela →
`NAO_MEDIDO`.

Exemplos (3 meses iguais, valores por mês):

| Caso | Conta à mão | Resultado |
| --- | --- | --- |
| Inflow 1.000, Outflow 900 | margem 10 % < 15 % | **Vulnerável** |
| Inflow 1.000, Outflow 800, variável 200 | razão 0,80; variável 600 ÷ 2.400 = 0,25 ≥ 0,1593; margem 20 % em 3 meses | Esbanjador e Livre são candidatos; vence **Esbanjador**. Pendência do Inflow médio registrada |
| O mesmo, com cheque especial no mês mais recente | cheque ativo → Vulnerável; o cheque também tira o Esbanjador | **Vulnerável** |
| Inflow 1.000, Outflow 850, variável 200 | razão 0,85 (ponta fechada); margem 15 %, não < 15 % | **Esbanjador** |
| Inflow 1.000, Outflow 600, variável 50 | razão 0,60 fora da faixa; margem 40 % em 3 meses | **Livre** |
| O mesmo, com má dívida 40 por mês | 120 ÷ 3.000 = 4 % < 10 % | **Livre** |
| O mesmo, com má dívida 100 por mês | 300 ÷ 3.000 = 10 %, não < 10 % | **SEM_SEGMENTO** |
| Meses 1.000/1.000, 1.000/500, 1.000/500 | total 3.000/2.000: margem 33,3 %, razão 0,667; só 2 meses com margem ≥ 15 % | **SEM_SEGMENTO** |
| Inflow 0, Outflow 300 | Surplus < 0 | **Vulnerável** |
| Inflow 0, Outflow 0 | sem movimento | **NAO_MEDIDO** |

Tudo conferido.

### 2.5 Flexibility e Behavior (`flexibility_score` e `behavior_score`, linhas 513-557)

**Flexibility** = 40 × margem + 30 × comprometimento + 30 × estabilidade, cada componente entre 0 e 1:

- margem = margem % ÷ 100, recortada em [0, 1];
- comprometimento = 1 − (fixos + parcelas) ÷ Inflow, recortado em [0, 1];
- estabilidade = meses com Surplus > 0 ÷ meses da janela.

**Behavior** = 100 − (40 × pen. margem + 35 × pen. crédito + 25 × pen. volatilidade):

- pen. margem = 1 − componente de margem;
- pen. crédito = fração dos meses com cheque especial ou crédito emergencial. Com o ajuste de Open Finance, vale 1;
- pen. volatilidade = coeficiente de variação amostral do Inflow mensal, recortado em [0, 1]. Com menos de 2 meses
  não se mede: vale 0 e sai a pendência `volatilidade_nao_medida_menos_de_2_meses`.

Inflow total 0 → score `None` (NAO_MEDIDO).

**Normalização sem saturação.** A margem é linear até 100 %. A medição com `clip(margem/0,15)` deu média
**exatamente 100,0** no Esbanjador e no Livre (`q_spec_diagnostico.json`, 09:17 BRT), porque qualquer margem acima de
15 % vira nota máxima. Com a divisão por 100, margem 20 % vale 0,2 e margem 60 % vale 0,6. Conferido.

Exemplo, 3 meses: Inflow 800, 1.000 e 1.200; Outflow 640, 800 e 960; fixo 300 e parcelas 100 por mês.

- Totais: Inflow 3.000, Outflow 2.400, margem 20 %.
- Flexibility: margem 0,2 × 40 = 8; comprometimento 1 − 1.200 ÷ 3.000 = 0,6 × 30 = 18; estabilidade 3 ÷ 3 × 30 = 30.
  Total **56**.
- Behavior: pen. margem 0,8 × 40 = 32; crédito 0; desvio padrão amostral de (800; 1.000; 1.200) = 200 e média 1.000,
  então CV = 0,2 × 25 = 5. Total 100 − 32 − 0 − 5 = **63**.
- Com cheque especial em 1 dos 3 meses: crédito 1/3 × 35 = 11,67. Total **51,33**.
- Com o crédito zerado pelo Open Finance: 100 − 32 − 35 − 5 = **28**.

Tudo conferido.

### 2.6 Open Finance (`ajustar_open_finance`, linhas 569-580)

- Surplus < 0 **e** patrimônio investido > R$ 50.000 (estritamente) → segmento "Esbanjador de Risco Controlado".
- Atraso em fatura externa > 15 dias (estritamente) → `zerar_componente_credito = True`, que no Behavior vira
  penalidade de crédito máxima (35 pontos).
- Dado ausente não muda nada e aparece em `nao_medidos`.

Exemplos: patrimônio 50.000,01 e atraso 16 dias com Surplus −100 → **Esbanjador de Risco Controlado** e crédito
zerado. Patrimônio 50.000 e atraso 15 dias → nada muda (as fronteiras não disparam). Surplus +500 com patrimônio
90.000 e atraso ausente → continua Livre, e `atraso_fatura_externa_dias` aparece como não medido. Tudo conferido.

### 2.7 As 19 escolhas que eram DECISAO_PENDENTE e agora estão DECIDIDAS

Decididas pelo aceite das 09:28. O nome da constante no código continua `DECISOES_PENDENTES` (linha 178), porque
este documento não edita código. A lista tem 19 itens (conferido às 09:32).

| # | Constante (linha) | Valor decidido | Ligada a |
| --- | --- | --- | --- |
| 1 | `ESBANJADOR_RAZAO_MAX_INCLUSIVO` (78) | `True`: faixa fechada 0,70 ≤ razão ≤ 0,85 | D-1 (referência) |
| 2 | `INFLOW_MEDIO_ALTO_MIN` (84) | `None`: critério não avaliado e declarado como pendência | D-1 |
| 3 | `DISCRICIONARIO_ALTO_FRACAO_OUTFLOW` (90) | 0,1593 = mediana da base (09:17) | D-1 |
| 4 | `INFLOW_ZERO_MARGEM` (95) | `None` (NAO_MEDIDO) | D-11 |
| 5 | `PRECEDENCIA_T3` (99) | Vulnerável > Esbanjador > Livre | D-1 |
| 6 | `SEM_SEGMENTO` (38) | rótulo próprio, sem forçar perfil | D-11 |
| 7 | `LIVRE_MESES_RECENTES_CONSECUTIVOS` (106) | `False`: 3 meses quaisquer | D-1 |
| 8 | `MESES_USO_ATIVO` (109) | 3 meses mais recentes | D-10 |
| 9 | `CHEQUE_ESPECIAL_PROXY_SALDO_NEGATIVO` (116) | `True` | D-10 |
| 10 | `CHEQUE_ESPECIAL_PROXY_MICRO_CHEQUE` (117) | `False` | D-10 |
| 11 | `FIXO_SUBCATEGORIAS` (121-127) | aluguel, condomínio, IPTU, energia, água | D-12 |
| 12 | `VARIAVEL_MACROS` (131) | Lazer, Lojas e sites, Restaurantes | D-1 |
| 13 | `JUROS_PAGOS_E_CREDITO_EMERGENCIAL` (138) | `False` | D-9 |
| 14 | `TARIFAS_SUBCATEGORIAS` (142-143) | duas tarifas = má dívida, não emergencial | D-19 |
| 15 | `MULTA_SUBCATEGORIAS` (144) | multa por atraso = má dívida (extensão nossa) | D-19 |
| 16 | `FINANCIAMENTO_COMPATIVEL_MAX_FRACAO` (148) | 0,30 do Inflow do mês | D-19 |
| 17 | `PARCELAS_SUBCATEGORIAS` (152-157) | quatro subcategorias de financiamento | D-12 |
| 18 | `MARGEM_TETO_PCT` (168) | 100 (linear, sem saturação) | D-12 |
| 19 | `ZERAR_CREDITO_E_PENALIDADE_MAXIMA` (173) | `True` | D-16 |

Há ainda uma escolha sem constante (linhas 175-176): a avaliação longitudinal roda com os meses que houver e marca
`completo = False`.

---

## 3. Duas regras T3 convivem

Pela D-1, a regra **oficial** é a de produção: `t3.py` e o SQL `visao_perfil_t3.sql`. Ela dá **45,3 / 28,6 / 26,1 %**
(n = 1.000, medido 04:06 BRT). A regra da **especificação** (`metricas_fluxo.classificar_t3_spec`) fica como
referência testada. Na média jan–nov ela dá **84,1 / 2,3 / 5,2 %, com 8,4 % sem segmento** (n = 1.000,
BigQuery 09:17 BRT, job `2fed39aa`).

| Ponto | Produção (oficial) | Especificação (referência) |
| --- | --- | --- |
| Base do cálculo | médias mensais da janela (`visao_perfil_t3.sql:15-18`) | soma dos meses da janela (`metricas_fluxo.py:461`); a margem é a mesma, a razão também |
| Janela | jan–nov/2025, meses completos antes do corte (`t3.py:8-9`) | os meses recebidos. A medição usou jan–nov |
| Inflow ≤ 0 | Vulnerável (`t3.py:101-102`; SQL `:26`) | Vulnerável se houver saída; `NAO_MEDIDO` sem movimento (`metricas_fluxo.py:462-463`) |
| Livre | margem ≥ 15 % na média, e nada mais (`t3.py:104-105`; SQL `:27`) | margem ≥ 15 % **e** 3 meses com margem ≥ 15 % **e** sem crédito emergencial **e** má dívida < 10 % (`metricas_fluxo.py:495-501`) |
| Esbanjador | margem < 15 %, mas (Surplus + discricionário) ÷ Inflow ≥ 15 %: cortar o discricionário devolve a folga (`t3.py:106-107`; SQL `:28`) | razão 0,70–0,85, variável ÷ Outflow ≥ 0,1593, sem cheque especial (`metricas_fluxo.py:480-493`). Pode ter margem acima de 15 % |
| Vulnerável | o resto (`t3.py:108`; SQL `:29`) | Surplus < 0 **ou** margem < 15 % **ou** crédito ativo nos 3 meses recentes (`metricas_fluxo.py:470-478`) |
| Discricionário / variável | 9 macros (`t3.py:49-57`): Lazer, Lojas e sites, Viagens, Restaurantes, Delivery, Assinaturas, Cuidados pessoais, Transporte por app, Pets | 3 macros (`metricas_fluxo.py:131`): Lazer, Lojas e sites, Restaurantes |
| Precedência | implícita na ordem do `if`: Livre é testado primeiro (`t3.py:104-108`) | Vulnerável > Esbanjador > Livre > SEM_SEGMENTO (`metricas_fluxo.py:99`, `:503-506`) |
| Sem segmento | não existe: todo cliente recebe um perfil | `SEM_SEGMENTO` (`metricas_fluxo.py:507-508`) |
| Cheque especial e dívida | não entram no T3; financiamento é "compromisso" (`t3.py:46-47`) | proxy de saldo negativo e má dívida entram (`metricas_fluxo.py:111-117`, `:345-359`) |

**Consequência.** Na produção, o Esbanjador é "quem voltaria a ter folga cortando o supérfluo", e isso separa a base
em três grupos de tamanho parecido. Na especificação, qualquer margem abaixo de 15 % leva a Vulnerável, e a faixa
estreita de razão (0,70–0,85) com a exigência de variável alto deixa o Esbanjador com 2,3 %. As diferenças que
importam estão escritas como `expectedFailure` em `tests/test_spec_t3_regras.py:160-190`: margem 10 % com
discricionário alto (produção: Esbanjador; especificação: Vulnerável), razão 0,80 com variável alto, cheque especial
ativo e a exigência de 3 meses estáveis.

---

## 4. Diagnóstico publicado (D-2)

A especificação traz um diagnóstico com **N = 316**, **28,8 %** em déficit, **19,6 %** com margem entre 0 e 15 % e
**48,4 %** críticos (28,8 + 19,6). Esses números **não devem ser publicados**. No lugar deles vão os números medidos:

| Recorte (n = 1.000) | Déficit | Margem 0–15 % | Crítico (soma) | Selo |
| --- | --- | --- | --- | --- |
| Média mensal jan–nov/2025 (janela da D-13) | 503 · **50,3 %** | 236 · **23,6 %** | 739 · **73,9 %** | `q_spec_diagnostico.json` `critico_janov` · 09:17 BRT |
| Dezembro/2025 inteiro | 316 · **31,6 %** | 181 · **18,1 %** | 497 · **49,7 %** | `critico_dez` · 09:17 BRT |
| Dezembro até 22/12 (data de corte) | 138 · **13,8 %** | 103 · **10,3 %** | 241 · **24,1 %** | `critico_dez22` · 09:17 BRT |

Todos: fonte `batalha-time-02-lxof.hackathon_dados.extrato_sintetico`, ADC, 48.828.427 bytes processados, job
`2fed39aa-3535-48c0-bc28-095edb2d96fb`. Base **sintética**.

**Por que o N = 316 se contradiz.**

1. Entre todas as hipóteses testadas, a única que dá exatamente 316 clientes é "déficit em dezembro, mês inteiro"
   (`hipoteses_que_dao_316 = ["deficit_dezembro_mes_inteiro"]`, 09:17 BRT).
2. Se o N = 316 é a coorte de quem teve déficit em dezembro, então **100 %** dessa coorte está em déficit em dezembro,
   e **0 %** está na faixa de margem 0–15 % (`distribuicao_recortes_316...critico_dez`: 316 e 0). Não pode ser 28,8 %
   nem 19,6 %.
3. Se, ao contrário, os percentuais se referem à base inteira, o déficit de dezembro é 31,6 %, não 28,8 %.
4. A varredura mês a mês, na base e na coorte, não encontrou nenhum casamento exato com 28,8 % ou 19,6 %
   (`varredura_28_8_e_19_6.casamentos_exatos = []`). O mês mais próximo de 28,8 % é novembro, com 29,3 %, que não
   é o mesmo número.

Conclusão: 316 e 28,8/19,6/48,4 % vêm de cortes diferentes, e nenhum corte da base reproduz os percentuais. O que se
publica é a tabela acima, com o selo, e a janela jan–nov como referência principal (D-13).

---

## 5. Etapa final: publicação no Cloud Run (código pronto; deploy NÃO EXECUTADO)

**Atualizado às 09:52 BRT.** Entre 09:44 e 09:52 o código ficou pronto para o Cloud Run (§5.2): settings lidos do
ambiente, `/healthz`, `Dockerfile`, `.dockerignore`, `gunicorn` no `requirements.txt` e 10 testes. **O deploy não foi
feito e não é deste agente.** Ele é a etapa final, depois do OK do Henrique. O levantamento original segue abaixo.

Levantado entre **09:33 e 09:38 BRT**, só com leitura: arquivos das três pastas, `gcloud config list` e
`gcloud run services list`. **Nenhum deploy foi feito.** Pela resposta do dono às 09:31, esta é a última etapa de todo
o processo e espera o OK do Henrique.

### 5.1 Como o deploy é feito hoje

**Achado principal.** Este backend (`backend-agente-conversacional`) e o clone publicado
(`old/desafio-itau-batalha-de-agentes-time2`) **não têm nenhum arquivo de deploy**: nem Dockerfile, nem
`cloudbuild.yaml`, `app.yaml`, `Procfile`, `service.yaml`, script ou workflow. O que está no Cloud Run é o **backend
do `agente-app-mobile`** (`agent_backend` + `deploy/`), não este Django.

| Item | Valor | Fonte |
| --- | --- | --- |
| Projeto GCP | `batalha-time-02-lxof` | `gcloud config list` (09:35); `agente-app-mobile/deploy/README.md:5` |
| Serviço existente | `i-agora`, região `us-central1`, pronto, revisão `i-agora-00006-22d` (generation 6) | `gcloud run services list` (09:35) |
| Quem criou | a conta do Henrique, em 2026-09-27T09:46Z (06:46 BRT) | idem |
| URLs | `https://i-agora-951291470271.us-central1.run.app` e `https://i-agora-7iv6efsgrq-uc.a.run.app`. `IAGORA_HOSTS` inclui também `i-agora.hsoares.com.br` | idem |
| Imagem | Artifact Registry `us-central1-docker.pkg.dev/batalha-time-02-lxof/agentes/i-agora`, com deploy por digest | idem; `deploy/README.md:36` |
| Recursos | 1 vCPU, 1 GiB, mínimo 0 e máximo 1 instância, concorrência 4, porta 8080, startup probe em `/api/health/` | idem; `deploy/README.md:38` |
| Conta de serviço | `squad-agent-sa@batalha-time-02-lxof.iam.gserviceaccount.com` | idem; `deploy/README.md:12` |
| Variáveis de ambiente | `IAGORA_HOSTS`, `IAGORA_STATE_BUCKET`, `IAGORA_RELEASE`, `IAGORA_DAILY_CALLS` (900), `IAGORA_BQ_MAX_BYTES` (100.000.000) | idem |
| Segredos (só o nome) | `GEMINI_API_KEY` ← `i-agora-gemini` versão 1; `DJANGO_SECRET_KEY` ← `i-agora-signing` versão 1 | idem; `deploy/README.md:11` |
| Banco | SQLite por sessão, materializado em `/tmp` e gravado no bucket GCS `iagora-state-951291470271` com `ifGenerationMatch`. Sem Cloud SQL; o Firestore está bloqueado | `deploy/README.md:9` |
| Estático | o `front_dist` vai dentro da imagem e é servido com `FileResponse`, sem whitenoise nem `collectstatic` | `deploy/Dockerfile:8`; `deploy/urls.py:7-13` |
| Servidor | `gunicorn deploy.wsgi:application --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 120`, com o usuário 10001 | `deploy/Dockerfile:1-11` |
| Comando de build e deploy | NAO_MEDIDO: nenhum arquivo traz o comando. A documentação diz "manual" e "por digest; segredos via Secret Manager" | `agente-app-mobile/docs/ambientes/ci-cd.md:13`, `:55` |
| Rollback | mandar o tráfego para a revisão anterior | `deploy/README.md:48` |

**Consequência para a decisão.** Há dois caminhos, e a escolha é do dono com o Henrique:

1. **Um serviço novo para este Django** (por exemplo `i-agora-conversacional`), ao lado do `i-agora`, com o mesmo
   projeto, região, conta de serviço e segredo. Não mexe no que o front usa hoje.
2. **Levar as rotas deste Django para o `agent_backend` do `agente-app-mobile`** e publicar no `i-agora` existente.
   Aproveita o deploy que já funciona, mas é um porte de código, e não uma cópia.

**Recomendação deste levantamento: o caminho 1, sem nunca sobrescrever o serviço `i-agora`.** Um
`gcloud run deploy i-agora` com a imagem deste Django derrubaria o backend que o front usa agora.

### 5.2 O que foi preparado neste Django para o Cloud Run (09:44–09:52 BRT)

Sem a variável de ambiente, o comportamento local é o de antes: `DEBUG` ligado, chave de desenvolvimento e qualquer
host. Os nomes `DJANGO_*` têm prioridade; `DEBUG`, `SECRET_KEY` e `ALLOWED_HOSTS` sem prefixo também são aceitos.

| Lacuna (09:35) | Estado às 09:52 | Onde | Teste |
| --- | --- | --- | --- |
| `DEBUG` fixo em `True` | **PRONTO.** `DJANGO_DEBUG` (padrão `1`; em produção, `0`) | `desafio_itau/settings.py:33` | `test_controle_debug_0_com_secret_key_sobe`; `test_local_sem_variaveis_mantem_o_comportamento_de_antes` |
| `SECRET_KEY` fixa | **PRONTO.** `DJANGO_SECRET_KEY`. Com `DJANGO_DEBUG=0` ela é obrigatória: sem ela, ou com a chave de desenvolvimento, o app **recusa subir** (`ImproperlyConfigured`) | `settings.py:35-45` | **prova negativa:** `test_prova_negativa_debug_0_sem_secret_key_recusa_subir` e `..._com_a_chave_de_desenvolvimento_recusa_subir` |
| `ALLOWED_HOSTS = ['*']` | **PRONTO.** `DJANGO_ALLOWED_HOSTS` (lista separada por vírgula). Local: `['*']`. Com `DEBUG=0` e sem a variável: lista vazia (o Django responde 400), nunca `*` | `settings.py:47-49` | `test_debug_0_allowed_hosts_vem_do_ambiente`; prova negativa `test_prova_negativa_debug_0_sem_allowed_hosts_nao_abre_para_todos` |
| HTTPS atrás do proxy | **PRONTO.** Com `DEBUG=0`: `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` e `CSRF_COOKIE_SECURE = True` | `settings.py:51-54` | `test_controle_debug_0_com_secret_key_sobe` |
| CORS e CSRF | **PRONTO** (D-5). `FRONT_ORIGENS` segue valendo para CORS e CSRF. Novo: `DJANGO_CSRF_TRUSTED_ORIGINS` soma origens só ao CSRF, sem abrir o CORS | `settings.py` (bloco da D-5, no fim) | `test_csrf_extra_do_ambiente_soma_as_origens_da_d5`; `tests/test_d5_origens_front.py` |
| Health | **PRONTO.** `GET /healthz` → 200 `{"status": "ok"}`, sem banco, BigQuery nem Gemini. É o **primeiro middleware**, antes da validação de host: a sonda do Cloud Run chega com Host interno. As rotas `conversas/status/` e `usuario-real/status/` continuam existindo, mas não servem de sonda porque podem ir à rede | `desafio_itau/saude.py`; `settings.py:70` | `test_healthz_200_sem_rede_e_sem_banco` (socket bloqueado, 0 consultas); provas negativas: rota comum com o mesmo Host dá 400, `POST /healthz` não é atalho |
| Servidor | **PRONTO.** `gunicorn>=22.0.0` no `requirements.txt`. Não instalado na venv local: o gunicorn não roda no Windows | `requirements.txt:12` | NAO_MEDIDO localmente |
| Imagem | **PRONTO.** `Dockerfile` na raiz: `python:3.12-slim`, `pip install -r requirements.txt`, usuário 10001, `DJANGO_DEBUG=0` e `SQLITE_PATH=/tmp/db.sqlite3`. Na partida roda `init_database.py` (migrate + 1.000 clientes demo, idempotente) e `gunicorn desafio_itau.wsgi:application --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 120`. Sem `collectstatic`: o projeto não tem pasta `static/` e as rotas do front são JSON | `Dockerfile` | `docker build`: **NAO_MEDIDO** (o docker não existe nesta máquina, conferido às 09:46). Partida simulada às 09:48 com `DJANGO_DEBUG=0` e `SQLITE_PATH` temporário: migrate e população OK |
| Contexto do build | **PRONTO.** `.dockerignore` exclui `db.sqlite3`, `.venv`, `archive/`, `relatorios/`, `notebooks/`, `skills/`, `.claude/`, `.secrets`, `.env*`, chaves e credenciais | `.dockerignore` | NAO_MEDIDO (sem docker) |
| Banco | SQLite em `SQLITE_PATH` (padrão local `BASE_DIR/db.sqlite3`; no contêiner, `/tmp`). **Efêmero**: ver item 5 da §5.3 | `settings.py:103-104` | — |
| Chave do Gemini | Sem mudança: `desafio_itau/segredos.py` lê primeiro a variável **`API_KEY_SECRECT`**, depois o arquivo `.secrets` (que não entra na imagem), depois `GEMINI_API_KEY`, `GSCONSOLE_SECRET` e `GOOGLE_API_KEY`. No Cloud Run: montar o segredo como `API_KEY_SECRECT`. O valor nunca é gravado | `segredos.py:19`, `:62-77` | — |
| Ledger de avaliação | grava em `relatorios/avaliacoes/*.jsonl`; o `Dockerfile` cria `/app/relatorios` com dono 10001. Disco efêmero: perde-se a cada revisão | `apps/conversas/interacao.py` | — |

Avisos conhecidos de `manage.py check --deploy` (09:48, com `DJANGO_DEBUG=0`): `W003` (sem `CsrfViewMiddleware`,
como antes; as views de `conversas/` conferem a origem por conta própria), `W004` (sem HSTS), `W008` (sem
`SECURE_SSL_REDIRECT`; o Cloud Run já só expõe HTTPS). `W009` e `W020` apareceram só porque a simulação usou uma chave
curta e nenhum host; somem com os valores reais.

### 5.3 Checklist de pré-requisitos

| # | Pré-requisito | Estado às 09:38 | O que falta |
| --- | --- | --- | --- |
| 1 | **D-7: repositório oficial** | DECIDIDO às 09:31: é o clone `old/desafio-itau-batalha-de-agentes-time2` (último commit `7f6a7c0`, 06:47, árvore limpa) | Copiar para o clone o que só existe aqui (lista abaixo) e fazer o commit local. O push só acontece com autorização explícita do dono no momento |
| 2 | Suíte completa verde | 517 testes às **09:53–09:54 BRT** (`python -m unittest discover -s tests`, rodado por mim): 1 FAIL, 21 expectedFailure e 1 unexpected success, os três no território da f7 em curso: `test_quatro_rotas.InteracaoTest.test_sem_x_sessao_id_401` espera `schema_version "1.0"` e recebe `"1.1"` (D9/D-15), e `test_i5_pergunta_de_seguimento_precisa_do_turno_anterior` passou (I5 feita). Os 10 testes do Cloud Run passam. Antes: 490 OK com 22 expectedFailure às 09:42 | Rodar de novo **depois** de a f7 fechar I4/I5/D9, e **no clone** depois da cópia |
| 3 | D-3, D-4 e D-5 aplicados | **D-3 e D-5 APLICADOS.** D-4 APLICADO no `perfil_usuario`; no `ConversationService` está com a f7 (aprovado 09:41) | A parte da f7 com teste verde |
| 4 | Migrações | **PRONTO:** `makemigrations --check --dry-run` → "No changes detected" às 09:51. A tabela da D-4 tem a migração `0002_sessao_perfil_usuario.py`. No contêiner, o `migrate` roda na partida (`init_database.py`) | Rodar de novo no clone depois da cópia |
| 5 | SQLite no Cloud Run | **Decidido para a demo: opção mínima.** O disco do contêiner é efêmero. **Mínima (é a que o comando da §5.4 usa):** `--min-instances 1 --max-instances 1`. A sessão dura enquanto a instância vive e **se perde a cada deploy** (e se o Cloud Run reciclar a instância). **Definitiva:** gravar a sessão num bucket GCS, como o `agente-app-mobile` faz (`deploy/README.md:9`, `ifGenerationMatch`); **não implementada**. Cloud SQL só com mais de uma instância | A definitiva fica para depois da entrega. A persistência da f7 (`apps/conversas/persistencia.py`, cache do Django no banco) usa o mesmo SQLite e tem o mesmo limite |
| 6 | Chave do Gemini vinda do Secret Manager | **PRONTO no código:** `API_KEY_SECRECT` é lida do ambiente (`segredos.py:62-65`). O segredo `i-agora-gemini` existe (versão 1). I9 resolvida (chave no cabeçalho) | Montar como `--set-secrets API_KEY_SECRECT=i-agora-gemini:1`, nunca como env de texto |
| 7 | `DEBUG=False` e `ALLOWED_HOSTS` | **PRONTO** (§5.2): `DJANGO_DEBUG`, `DJANGO_SECRET_KEY` (obrigatória com `DEBUG=0`) e `DJANGO_ALLOWED_HOSTS` | Criar o segredo da `DJANGO_SECRET_KEY` (proposta abaixo) |
| 8 | CSRF e CORS com a URL do front de produção | **PRONTO no código:** `FRONT_ORIGENS` (CORS e CSRF) e `DJANGO_CSRF_TRUSTED_ORIGINS` (só CSRF) vêm do ambiente | A URL do front de produção é NAO_MEDIDO. Sem ela, só a URL do próprio serviço entra no CSRF |
| 9 | BigQuery na conta de serviço | NAO_MEDIDO: não se conferiu se `squad-agent-sa` tem `bigquery.jobUser` e leitura em `hackathon_dados` | Conferir o IAM antes do deploy |
| 10 | CSV da verdade na imagem | `data/usuarios_verdade.csv` só existe aqui | Entra na cópia do item 1 e no Dockerfile |
| 11 | Ledger | grava em disco efêmero | Aceitar a perda na demo ou gravar no bucket |
| 12 | **Regra "sem o dono e o Henrique"** | Nada é publicado sem os dois. O dono já disse às 09:31 que o Cloud Run espera o OK do Henrique | OK explícito do dono e do Henrique, na hora |
| 13 | `/healthz` para a sonda | **PRONTO** (§5.2) | Usar como startup probe no deploy |
| 14 | `docker build` local | **NAO_MEDIDO:** o docker não existe nesta máquina (09:46). O `gcloud builds submit` da §5.4 é o primeiro build real | Não é bloqueio: o Cloud Build constrói a partir do `Dockerfile` |

**O que copiar para o clone (item 1).** A comparação foi feita só por leitura, às 09:35, ignorando `.venv`,
`__pycache__`, `*.pyc`, `db.sqlite3` e `.git`. Resultado: 93 arquivos existem só aqui; 24 dos 302 arquivos comuns
diferem; 45 existem só no clone.

Só aqui (copiar):

- `apps/conversas/` inteiro, com 34 arquivos: views, `views_interacao`, urls, service, gateway, rules, schemas,
  projection, estado, context, fairness, extremos, os quatro `interacao*.py`, `fluxos_comportamento.json`, `prompts/`
  (12 arquivos) e `knowledge/` (4).
- `apps/context_agent_datadriven/services/perfil_usuario.py`, `services/metricas_fluxo.py` e
  `views_perfil_usuario.py`.
- `desafio_itau/politica/`, com 8 arquivos: `__init__`, `erros_api.py`, `lexico.py` e os JSON `comunicacao`,
  `erros_api`, `lexico`, `operacional` e `produtos-v1`. Não se conferiu se `desafio_itau/segredos.py` existe no clone
  (NAO_MEDIDO).
- `data/usuarios_verdade.csv` e `data/usuarios_verdade.selo.json`.
- `datasets/` (4 arquivos), `scripts/` (6: `avaliar_llm`, `baixar_usuarios_verdade`, `conferir_rc8_oficial`,
  `contratos_corpos.json`, `gemini_trabalho_pesado`, `verificar_base_lida`) e `tests/` (25 arquivos novos).
- Em `docs/`: `backlog.md`, `desenho-respostas-por-interacao.md`, `rc8-rastreabilidade-2026-09-27.md`,
  `relatorio-migracao-politica-2026-09-27.md`, `rota-integrada-batalha-agentes-backend.md`, as medições de
  `estudo-i-agora/medicoes/2026-09-27/` e este documento.
- Não copiar: `.claude/settings.local.json` (configuração local), `db.sqlite3` (ignorado pelo git do clone,
  `.gitignore:3`) e qualquer `.secrets`. A pasta `relatorios/` é saída de execução: decidir se entra.

Nos dois, mas diferentes (substituir no clone depois de revisar o diff; entre parênteses, as linhas alteradas):

- Em `apps/context_agent_datadriven/`: `views.py` (123), `services/agente_service.py` (118), `models.py` (71),
  `views_controle_conversa.py` (12), `conversa/roteiro.json` (11), `agentes/LLM_Models/google/cliente.py` (9),
  `urls.py` (6), `i_agora/t3.py` (6), `i_agora/consultas.py` (5) e `templates/context_agent_painel_html.py` (2).
- Em `desafio_itau/`: `settings.py` (27), `modelos_llm.py` (28) e `urls.py` (4, monta `conversas/`).
- Em `docs/`: `contrato-api-frontend.md` (233), `architecture.md` (124), `fluxos-de-conversacao.md` (112), `INDICE.md`
  (16) e `CHANGELOG-semantica.md` (10).
- `tests/test_controle_conversa.py` (40), `README.md` (10) e `requirements.txt` (1: `python-liquid==2.3.2`).
- `.gitignore` (1): o clone tem `.venv-agent/`, e essa linha deve **ficar**.
- `.claude/skills/` (2): pela regra do dono, as skills não entram no commit.

Só no clone (manter, não apagar): `agent_backend/` (41 arquivos, a origem do porte para `apps/conversas/`),
`docs/ci/conversation.yml`, `docs/estrutura.md`, `docs/i-agora.md` e `scripts/secret_scan.py`.

A cópia é o **último passo antes do deploy** (D-7 escolhida). Ela espera a f7 fechar I4/I5/D9; copiar antes leva código pela metade. Somam-se à lista os arquivos do Cloud Run: `Dockerfile`, `.dockerignore`, `desafio_itau/saude.py`, `tests/test_cloud_run_prontidao.py`, e as versões novas de `desafio_itau/settings.py`, `requirements.txt` e `scripts/primeira_interacao.py`.

### 5.4 Comando de deploy que SERIA rodado: NÃO EXECUTADO

> **NÃO EXECUTADO.** Só pode rodar com o OK explícito do dono e do Henrique, depois de todo o checklist da §5.3. O deploy
> não é deste agente. O serviço é **NOVO**: `i-agora-conversacional` (proposta). **Nunca** `i-agora`, que é do Henrique e
> roda o backend do `agente-app-mobile`: um deploy com esse nome derrubaria o front que está no ar.

```bash
# NÃO EXECUTADO. Rodar a partir do clone oficial (D-7), depois da cópia e do commit local.
PROJETO=batalha-time-02-lxof
REGIAO=us-central1
SERVICO=i-agora-conversacional          # serviço NOVO, proposta; NUNCA i-agora
TAG=$(git rev-parse --short HEAD)
IMAGEM=us-central1-docker.pkg.dev/$PROJETO/agentes/$SERVICO:$TAG
# URL determinística do Cloud Run: <serviço>-<número do projeto>.<região>.run.app (número 951291470271, da URL do i-agora)
HOST=$SERVICO-951291470271.us-central1.run.app

gcloud builds submit --project "$PROJETO" --tag "$IMAGEM"

gcloud run deploy "$SERVICO" \
  --project "$PROJETO" --region "$REGIAO" \
  --image "$IMAGEM" \
  --service-account squad-agent-sa@batalha-time-02-lxof.iam.gserviceaccount.com \
  --port 8080 --cpu 1 --memory 1Gi \
  --min-instances 1 --max-instances 1 --concurrency 4 \
  --startup-probe httpGet.path=/healthz,httpGet.port=8080 \
  --set-secrets "API_KEY_SECRECT=i-agora-gemini:1,DJANGO_SECRET_KEY=i-agora-conversacional-django:1" \
  --set-env-vars "DJANGO_DEBUG=0,DJANGO_ALLOWED_HOSTS=$HOST,DJANGO_CSRF_TRUSTED_ORIGINS=https://$HOST,SQLITE_PATH=/tmp/db.sqlite3,USUARIO_REAL_ATIVO=1,USUARIO_REAL_PROJETO=batalha-time-02-lxof,CONVERSAS_MODO=demo_live,CONVERSAS_MAX_CHAMADAS=300" \
  --allow-unauthenticated
```

Variáveis e segredos (só os nomes; nenhum valor é gravado):

| Nome no contêiner | Tipo | Origem | Observação |
| --- | --- | --- | --- |
| `API_KEY_SECRECT` | segredo | `i-agora-gemini:1` (existe) | Nome que `desafio_itau/segredos.py:19` lê primeiro |
| `DJANGO_SECRET_KEY` | segredo | `i-agora-conversacional-django:1` (**proposta, ainda não existe**) | Obrigatória com `DJANGO_DEBUG=0`. Um segredo próprio evita que um cookie assinado por um serviço valha no outro. Reusar `i-agora-signing` é possível, mas a decisão é do Henrique |
| `DJANGO_DEBUG` | env | `0` | Já vem `0` no `Dockerfile`; repetido aqui por clareza |
| `DJANGO_ALLOWED_HOSTS` | env | host `*.run.app` do serviço | A URL com hash (`...-uc.a.run.app`) só se conhece depois do deploy: acrescentar com `gcloud run services update --update-env-vars`. Para mais de um host, usar o delimitador alternativo do gcloud (`^@^`), porque a vírgula separa as variáveis |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | env | `https://` + host | Só CSRF |
| `FRONT_ORIGENS` | env | NAO_MEDIDO | Origem do front de produção, se ele chamar este serviço de outro domínio (CORS + CSRF). Sem ela, valem as origens locais da D-5 |
| `SQLITE_PATH` | env | `/tmp/db.sqlite3` | Já no `Dockerfile` |
| `USUARIO_REAL_*`, `CONVERSAS_*` | env | valores acima | Iguais aos de hoje |

Observações:

- **Sessão:** `--min-instances 1 --max-instances 1` é a **opção mínima** do item 5 da §5.3. A sessão vive enquanto a
  instância vive e se perde a cada deploy. A opção definitiva (bucket GCS) não está implementada.
- `--startup-probe` com `httpGet`: a sintaxe depende da versão do gcloud (NAO_MEDIDO nesta máquina). Sem ela, a sonda
  TCP padrão na porta 8080 também serve, e o `/healthz` fica para o teste de fumaça.
- `--allow-unauthenticated` segue o serviço `i-agora`, que o front chama sem login. A decisão é do Henrique.
- Antes do deploy: conferir o IAM da conta de serviço no BigQuery (item 9 da §5.3) e criar o segredo
  `i-agora-conversacional-django`, com valor gerado na hora e nunca escrito em arquivo.

### 5.5 Teste de fumaça depois do deploy: NÃO EXECUTADO

```bash
# NÃO EXECUTADO
URL=$(gcloud run services describe i-agora-conversacional --region us-central1 \
  --project batalha-time-02-lxof --format="value(status.url)")

# 1. Health: não toca em banco, BigQuery nem Gemini
curl -s "$URL/healthz"
#    espera 200 e {"status": "ok"}

# 2. BigQuery com a conta de serviço
curl -s "$URL/api/v1/context-agent/usuario-real/status/?validar=1"
#    espera 200 e "conexao": "VALIDADA"

# 3. Status do harness de conversa
curl -s "$URL/api/v1/context-agent/conversas/status/"
#    espera 200, com o modelo configurado e o orçamento

# 4. Uma interação com usuário real (índice 1 do CSV da verdade)
SESSAO=$(curl -s -X POST "$URL/api/v1/context-agent/perfil-usuario/definir/" \
  -H "Content-Type: application/json" -d '{"usuario": "1"}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['sessao_id'])")
curl -s -X POST "$URL/api/v1/context-agent/conversas/interacao/" \
  -H "Content-Type: application/json" -H "X-Sessao-Id: $SESSAO" \
  -d '{"etapa": "home.visao_conta"}'
#    espera 200, schema_version "1.1", origem_resposta "dados", selo presente

# 5. Prova negativa: sem X-Sessao-Id tem de dar 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$URL/api/v1/context-agent/conversas/interacao/" \
  -H "Content-Type: application/json" -d '{"etapa": "home.visao_conta"}'
#    espera 401

# 6. Prova negativa: a rota antiga tem de dar 410 (D-3)
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$URL/api/v1/context-agent/enviar-mensagem/"
#    espera 410
```

O teste passa quando: 1 dá 200 `{"status": "ok"}`; 2 dá 200 com a conexão ao BigQuery validada; 3 dá 200; 4 dá 200,
com `selo` e com `perfil_t3` diferente de `NAO_MEDIDO`; 5 dá 401; 6 dá 410. Depois, repetir o passo 4 numa segunda
chamada com o mesmo `SESSAO`, para confirmar que a sessão sobreviveu entre pedidos (D-4, dentro da mesma instância).

### 5.6 O que bloqueia o Cloud Run hoje (09:52 BRT)

1. A regra do dono: falta o **OK do Henrique**, e o do dono na hora.
2. A **f7** ainda está fechando I4 no `ConversationService`, I5 e D9 (aprovado às 09:41).
3. **D-7**: a cópia para o clone é o último passo antes do deploy e ainda não foi feita.
4. O segredo `i-agora-conversacional-django` não existe (ou o Henrique decide reusar `i-agora-signing`), e o IAM do
   BigQuery na conta de serviço é NAO_MEDIDO.
5. O código deste Django **está pronto** para o Cloud Run (§5.2). O `docker build` é NAO_MEDIDO (sem docker aqui).
