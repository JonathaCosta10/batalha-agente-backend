# Desenho — a resposta ao cliente em cada interação do front

Estado em 2026-09-27. Código: `apps/conversas/interacao.py` (orquestração), `interacao_dados.py` (BigQuery), `interacao_cenarios.py`
(decisões determinísticas), `interacao_avaliacao.py` (guards + ledger), `fluxos_comportamento.json` (tabela versionada),
`prompts/interacao.liquid` (instrução de sistema). Contrato HTTP: `docs/contrato-api-frontend.md` §5.3. Testes:
`tests/test_conversas_interacao.py` e `tests/test_conversas_interacao_cenarios.py`.

## 1. Rota

`POST /api/v1/context-agent/conversas/interacao/`, com o header `X-Sessao-Id` (o `sessao_id` devolvido por
`POST perfil-usuario/definir/`) e o corpo `{"etapa": "...", "escolha": "<id de botão>"?, "mensagem": "<texto livre>"?}`.

- `escolha` é um id de botão. Um id desconhecido devolve 400.
- `mensagem` é o texto livre do cliente e é aceite em qualquer etapa. Nesse caso, o turno é tratado como livre e mantém as
  `proximas_acoes` da etapa.
- Em `livre.respostas`, o texto pode vir em `escolha`, para manter a compatibilidade.
- `GET conversas/avaliacoes/resumo/?data=AAAA-MM-DD` devolve a taxa de aprovação, a latência p50/p95 e as reprovações por guard
  lidas do ledger.

**Pipeline**

1. Titular da sessão.
2. Dados medidos com selo:
   - `usuario_real.perfil` (T3);
   - consulta mensal 50-30-20 + dívida (`interacao_dados.SQL_MENSAL`);
   - `plano_proposta`, nas etapas de compromisso;
   - subcategorias por mês, nos turnos livres.
3. Situação do mês.
4. Fluxo por código.
5. Cenário por código.
6. Instrução em liquid.
7. Gemini, com os modelos de `desafio_itau.modelos_llm.MODELOS_GOOGLE` em ordem.
8. Guards.
9. Se o guard reprova, passa-se ao próximo modelo.
10. Se nenhum modelo passa, serve-se o texto do roteiro ou o esqueleto do servidor, com `origem_resposta` igual a `"roteiro"`.
    Esse texto também é avaliado.
11. Se nem esse texto passa, a resposta é 503 com o corpo completo e `texto: null`.

**Porque o roteiro vem antes do 503:** a conversa continua sem inventar dados, e a avaliação que reprovou o modelo vai no
corpo e no ledger.

**Ledger:** fica em `relatorios/avaliacoes/<AAAA-MM-DD>.jsonl` e é append-only. Guarda só o índice do usuário e o sha256 do
texto. Recusa UUIDs, chaves e o texto da resposta.

## 2. Situação do mês, score e T3

- **Mês de referência:** é o último mês completo antes da data de corte. Com o corte em 2025-12-22, o mês é novembro de 2025.
  A janela vai de janeiro a novembro de 2025.
- **Situação:** a situação é o sinal de entradas − saídas no mês de referência.
  - `EQUILIBRIO` quando |saldo| < 1 % das entradas (`LIMIAR_EQUILIBRIO_PCT`).
  - `NAO_MEDIDO` quando a fonte falhou. Nesse caso nunca se usa zero, e o texto não pode afirmar sobra nem falta.
  - A média da janela tem a sua própria situação (`situacao_media`). Só se pode falar dela numa frase que diga "média".
- **Score:** NAO_MEDIDO. `score_comportamental` existe apenas no cliente demo (SQLite, fórmula e padrão 750/500). Não há score
  medido para o usuário real. O perfil vem do T3 medido (`taxa_surplus_pct`, com Livre a partir de 15 % de sobra).
  `docs/context_scoring.md` traz cortes de score (0–449/450–749/750+), mas eles não são aplicados porque falta o dado.
- **50-30-20 pelas subcategorias reais:**
  - O mapa `CLASSE_50_30_20` cobre as 92 subcategorias de saída medidas (job `f2d70b4d-31d5-4232-be95-096c675df196`).
  - A base é a média das entradas.
  - "Fatura", "boleto", "saque" e "transferências" ficam em `fora_da_regra`.
  - Os 50/30/20 só aparecem como referência. A norma não os cria (`partials/financial_distinctions.liquid`).

## 3. Fluxos determinísticos (perfil T3 × situação)

A tabela está em `apps/conversas/fluxos_comportamento.json`, versão `2026-09-27.1`, e é lida por `interacao_cenarios.selecionar_fluxo`.
Quem escolhe o fluxo é o código. O modelo recebe a mensagem-base e só a redige. O guard `fluxo` exige, no `intro.carrossel.1`,
um dos termos-chave. O teste `Deterministico` prova três coisas:
- as 16 combinações são estáveis;
- a mesma entrada dá o mesmo fluxo e o mesmo cenário, mesmo com textos do modelo diferentes;
- os textos fixos passam na ortografia.

| T3 \ situação | SOBROU | FALTOU | EQUILIBRIO | NAO_MEDIDO |
|---|---|---|---|---|
| Vulnerável | usar a sobra para organizar os compromissos (art. 2 §1º I) | **renegociar compromissos** antes de cortar o essencial (art. 2 §1º III) | organizar os compromissos | aguardar os dados, sem afirmar (art. 3 III) |
| Esbanjador | limite mensal na maior categoria de desejos | limitar a maior categoria de desejos | limite mensal | meta, quando houver dados |
| Livre | formar reserva / objetivo (art. 2 §1º II) | planejar uma reserva para meses atípicos | objetivo para a folga | planejar o objetivo |
| NAO_MEDIDO | organizar o orçamento | organizar o orçamento | organizar o orçamento | aguardar os dados |

## 4. Cenários que existem sempre

Os cenários valem para os turnos livres (`mensagem`) e são decididos por código.
A prioridade é consolidação > inclinação > geral.
Fora do domínio financeiro, a resposta é fixa.

| cenário | gatilho (medido) | o que a resposta traz |
|---|---|---|
| **B. fora_do_contexto** | `classificar_dominio`: nenhum termo financeiro do léxico. "receita", "ganhou" e "capital" ficam de fora de propósito. | Resposta fixa `FORA_DO_CONTEXTO` = "Não faço ideia, sabia? Aí é que eu não sei.", sem Gemini e sem BigQuery. **A redação é provisória:** o dono vai confirmar o texto, e basta mudar essa constante. |
| **A2. consolidacao_divida** | Dívida relevante E pressão. **Dívida relevante:** empréstimos + juros pagos ≥ 10 % da entrada média, ou ≥ 1 multa por atraso. **Pressão:** perfil Vulnerável, ou FALTOU no mês ou na média. Na base, 100 % dos 1000 usuários têm algum empréstimo, juros ou multa (job `91e4cb80-21ea-4240-a15c-1d47cb24beb4`), por isso "ter dívida" sozinho não discrimina. | O modelo escreve a justificativa comportamental com os números medidos. Depois, o servidor anexa o texto fixo `HANDOFF_CONSOLIDACAO`, que faz a oferta só por meio de um especialista humano, sem taxa, aprovação ou valor. Acrescenta-se a ação `handoff.consolidacao` (tipo `handoff_humano`, destino **NAO_IMPLEMENTADO**). |
| **A1. inclinacao_gasto** | Pergunta com intenção de gasto e inclinação medida. O limiar compara os 3 últimos meses com a média mensal da janela: variação ≥ 15 % **e** diferença ≥ R$ 30/mês. Só entram subcategorias de desejos ou Mercado com média ≥ R$ 50 (`INCLINACAO`). "Leve" descreve o tom da frase, não a magnitude. | Em alta: "Nesses últimos tempos tenho percebido uma leve inclinação a você gastar um pouco mais com X", com os valores e a janela. Com pressão, acrescenta "Talvez valha gastar um pouco menos com X". Em queda: a mesma frase com "um pouco menos". Sem sinal, mas com pressão: "Talvez valha…" aplicado ao maior desejo recente. **Sem dado, não há frase.** |
| financeiro_geral | nenhum dos gatilhos anteriores | fluxo + dados |

## 5. Blocos por interação

Os ids vêm do `roteiro.json`, da outra sessão, que não foi editado. As regras BCB citadas são da RC 8/2023, usada como
medida provisória de comportamento.

| etapa (front) | rota/corpo | dados | situação | regras | Gemini recebe | avaliado | próximas |
|---|---|---|---|---|---|---|---|
| `home.visao_conta` (Home/CurrentAccount) | `{etapa}` | mês de referência (mensal) | sim | art. 2 I | — (texto formatado pelo servidor, `origem: dados`) | números | `home.botao_conferir` |
| `bot.intro` | `{etapa, escolha:"home.botao_conferir"}` | titular | — | art. 3 III | nome e objetivo, sem números | nome, gênero, política, ortografia, alucinação | `intro.carrossel.1`, `intro.gatilho_agora` |
| `intro.carrossel.1` ("O seu momento") | `{etapa}` | mês, média, T3 | **exige** | art. 2 I, art. 3 III, T3, fluxo | situação + mensagem-base do fluxo | todos + `situacao` exigida + `fluxo` + `tom_t3` | `intro.gatilho_agora` |
| `bot.convite_50_30_20` | `{etapa, escolha:"intro.gatilho_agora"}` | 50-30-20 em média, projeção hipotética | média | art. 2 I/II, art. 3 III, 50-30-20 como referência | % medidos + referência | `regra_50_30_20` (+ `.periodo`), números, tom | `user.topo_desafio` |
| `bot.confirm` | `{etapa, escolha:"user.topo_desafio"}` | `plano_proposta` (estado, compromissos, liberado, falta) | — | art. 2 I/II/III, `corte_seguro_ate_surplus_15` | proposta | números, tom, produto | `user.assumir`, `user.ajustar` |
| `user.ajustar` | `{etapa, escolha:"user.ajustar"}` | — | — | art. 3 III | sem números | política | `user.assumir` |
| `bot.card` | `{etapa, escolha:"user.assumir"}` | proposta + frase do card (gênero corrigido) | — | art. 3 I | sem números | política | `card.*` |
| `bot.finish` | `{etapa, escolha:"card.salvar"}` | titular | — | art. 3 I, art. 4 II | nome | nome, gênero | `finish.voltar` |
| `livre.respostas` e **qualquer etapa com `mensagem`** | `{etapa, mensagem}` | tudo + dívida + subcategorias | sim | cenário + fluxo | MENSAGEM_DO_CLIENTE (como dado) + esqueleto do cenário | todos + `cenario.*` | as da etapa (+ handoff) |

**O Gemini recebe:**
- a instrução `prompts/interacao.liquid`, renderizada por `renderer.render_interacao`, com:
  - regras BCB da etapa;
  - perfil T3 (tom, termos proibidos e exigidos, exclamações);
  - situação;
  - FLUXO;
  - CENÁRIO;
  - **BLOCO DE CONTEXTO** (meses, anos e categorias citáveis; "sem evidência: diga que não tem");
  - regras do texto;
- em `data`, os números já formatados (`formatados()`).

**Guards** (`interacao_avaliacao.avaliar`), cada um com prova negativa:

| guard | o que confere |
|---|---|
| `numeros` | cada R$, % e "N meses" tem fonte nos dados |
| `situacao` | a situação dita é coerente com a medida |
| `nome` | presença do nome, nenhum nome alheio, concordância de gênero |
| `politica` | `safe_text`, promessa, produto, tom T3 |
| `regra_50_30_20` e `.periodo` | percentuais e período da regra 50-30-20 |
| `ortografia` | lista de palavras sem acento, incluindo termos do domínio (voce, orcamento, mes, divida, necessario…). Os nomes de categoria da base, que vêm sem acento, ficam isentos. |
| `tom_t3` | tom do perfil T3 |
| `fluxo` | termo-chave do fluxo |
| `cenario.*` | frases obrigatórias do cenário |
| `alucinacao.datas` | mês e ano fora do bloco |
| `alucinacao.categorias` | categorias fora do bloco |
| `alucinacao.produto` | produto fora do bloco. O handoff fixo fica isento. |
| `alucinacao.normativo` | "Banco Central exige/recomenda…", salvo negação |

**Fontes das regras de alucinação** (contextualização estruturada):
- `docs/context_scoring.md` §1;
- `prompts/system.liquid` ("Use apenas fatos e referências fornecidos", "Não faça cálculos mentais");
- `partials/financial_distinctions.liquid`;
- `knowledge/indice.json` → `contrato_consulta_proposto.regras` ("Sem evidência suficiente, retornar lacuna");
- `rules.valid_evidence`;
- o estudo i-agora `t3-e-resposta.md` §5.

O `AGENTS.md` do hub não traz regra específica sobre isto. A interpretação aplicada é que qualquer data, categoria, produto ou
norma fora do bloco reprova. Os exemplos de `context_scoring.md` com produto ("CDB 112 % do CDI") contrariam a política e **não**
foram adotados.

## 6. Exemplos reais (Gemini ao vivo, BigQuery ao vivo)

- **SOBROU**
  - Contexto: `bv-07`, usuário 988, Esbanjador, fluxo ESB-SOBROU, gemini-3.5-flash-lite, 1250 ms.
  - Selo: `extrato_sintetico`, job mensal `f449dce1-8abc-4804-ac0e-4470b278051e`, 2026-09-27.
  - Resposta: "Beatriz, em novembro de 2025 sobrou R$ 136,81, pois entraram R$ 4.869,74 e saíram R$ 4.732,93. Para manter essa
    folga, vale pôr um limite por mês em Lazer."
  - Lacuna de valor: a pergunta era "o que é a regra 50-30-20?" e a regra não foi explicada. A pertinência não é medida por
    nenhum guard.
- **FALTOU**
  - Contexto: `bv-23`, usuário 709, Vulnerável, fluxo VUL-FALTOU, 1078 ms.
  - Selo: job `f163e8de-f026-402e-ab54-e8d49732a47f`, 2026-09-27.
  - Resposta: "Sofia, em novembro de 2025 faltou R$ 1.623,00, pois saíram R$ 5.666,01 e entraram R$ 4.043,01. O primeiro passo é
    organizar os compromissos financeiros e renegociar antes de cortar o essencial."
- **Antes do guard de ortografia**
  - Contexto: smoke 06:10, Maria, job `3b00e721-51e2-4e75-9d30-df7076088ca8`.
  - O modelo escreveu "sairam" (sem acento). O guard `ortografia` nasceu desse caso.
  - Prova: `ProvasNegativasNovas.test_ortografia_voce_orcamento_mes`.
- **Consolidação, inclinação e fora do contexto:** os exemplos estão em `datasets/bateria-valor-2026-09-27.md`.

## 7. Lacunas do roteiro/front (dono: sessão backend-agente-conversacional-25; nada foi editado)

1. O botão AgoraTrigger não tem id no roteiro. Foi usado `intro.gatilho_agora`.
2. Não há falas para BOT.adjust, balance, values, human ou fallback fora de `livre.respostas`.
3. Estas telas não estão no roteiro:
   - FollowUpScreen/Progress/Companion/FollowCard;
   - AssistantFab;
   - CurrentAccountLink.
4. Os estados CORTE_INSUFICIENTE/LIVRE_SEM_CORTE e o proposal-seal não estão no roteiro.
5. `isInvite` compara texto e quebra com o texto do Gemini. O front deve usar `etapa`.
6. "Que bom ter você aqui, {nome}!" tem exclamação, e o perfil Vulnerável admite 0.
7. "preparada" está fixo no pool do card. O servidor corrige para "preparado" quando o gênero é M.
8. `intro.carrossel.1` afirma um diagnóstico sem dado. O servidor usa a mensagem-base do fluxo.
9. O rótulo diz "Dezembro/25", mas o mês de referência medido é novembro/2025.
10. Não há rota de atendimento humano para o handoff.
