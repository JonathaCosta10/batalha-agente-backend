# Controle da conversa

O **controle da conversa** é o registro, no backend, de toda fala que a pessoa vê no app. Cada fala tem
um id estável, o estágio em que aparece, as variáveis que usa, a fonte atual no front e a fonte-alvo no
backend. A partir deste documento, nenhuma fala nova entra no front sem entrar primeiro aqui.

| Peça | Caminho |
| --- | --- |
| Roteiro (fonte única) | [`apps/context_agent_datadriven/conversa/roteiro.json`](../apps/context_agent_datadriven/conversa/roteiro.json) |
| Rota | `GET /api/v1/context-agent/controle-conversa/[?estagio=<estagio>]` |
| Validação | `carregar_roteiro()` em [`views_controle_conversa.py`](../apps/context_agent_datadriven/views_controle_conversa.py) |
| Testes | [`tests/test_controle_conversa.py`](../tests/test_controle_conversa.py) |

O levantamento foi feito em **2026-09-27 às 05:36 BRT** no código de `frontend-agent-conversacional/src`. As
referências `arquivo:linha` do roteiro são relativas a essa pasta.

## 1. O que foi medido no front

- **O front não chama nenhuma API.** Não há `fetch`, axios nem XHR em `src/`. Todo texto é fixo ou
  calculado no navegador, e o estado fica no `localStorage` (`i-agora-maria-janeiro-2026-v4` e
  `i-agora-pessoas-v1`).
- **As pessoas são inventadas no front.** A abertura 0 é sempre `MARIA` (`data/people.ts:7-10`). As
  seguintes saem de `calculatePerson(id)`, em que id par é F e id ímpar é M. A abertura 1 é **Alexandre**.
- **O dinheiro da home é fórmula, não dado.** Maria tem Entradas 5.000 e Saídas 5.380, logo Saldo −380.
  Os outros valores vêm de fórmulas em `personService.ts`. "Dezembro/25" e "JANEIRO / 2026" são
  constantes.
- **`genero` nunca entra em texto.** A frase "…vão me encontrar mais **preparada**" é feminina para
  todo mundo, inclusive para o Alexandre.
- **Só a categoria delivery é alcançável.** "Topo o desafio" fixa `selected=['delivery']` e nenhuma tela
  muda essa seleção. Os compromissos de compras, outros e reserva existem, mas nunca aparecem.
- **A bolha do convite é reconhecida por igualdade exata de texto** (`isInvite`). Se o backend mandar outro
  texto, quebram o itálico e a rolagem. Para trocar o texto, é preciso mudar primeiro o front, que passa a
  reconhecer a bolha pelo id `bot.convite_50_30_20`.
- **A legenda do chat diz "sem acesso aos dados da conta".** Ela deixa de ser verdade no dia em que o
  front usar `usuario-real`.

## 2. Máquina de estados (hoje, no front)

`hooks/usePlanConversation.ts`. `speak()` põe a bolha do usuário, mostra "digitando" por **650 ms**
(`TYPING_DELAY`) e depois põe a bolha do bot e troca o estágio.

```
home --Conferir / Planejar janeiro / FAB--> intro  (bot.intro + carrossel de 2 cartões)
intro --logo i.agora--> invite                      (bot.convite_50_30_20)
invite --"Topo o desafio"--> confirm                 (bot.confirm + painel; selected=['delivery'])
confirm --"Ajustar valores"--> confirm               (BOT.adjust)
confirm --"Assumir meus compromissos"--> card        (bot.card + card com frase)
card --"Gerar outra frase"--> card                   (frase seguinte, sem mensagem)
card --Salvar imagem / Baixar PNG com sucesso--> finish (bot.finish)
qualquer --texto livre--> mesmo estágio              (resposta por palavra-chave)
Reiniciar / Recomeçar planejamento -> mesma pessoa, volta a intro; o próximo "Conferir" troca de pessoa
```

## 3. As falas das telas enviadas pelo dono

| Tela | Trecho | id no roteiro | Variáveis |
| --- | --- | --- | --- |
| Home | Olá, Maria | `home.saudacao` | `primeiro_nome` |
| Home | Organizar suas finanças pode ser tão simples… | `home.convite` | — |
| Home | Pix e transferir · Pagar · Cartão virtual · Planejar janeiro | `home.atalhos` | — |
| Home | VISÃO DA CONTA · Dezembro/25 | `home.visao_conta.titulo` | `periodo_saldo` |
| Home | Saldo do mês −R$ 380,00 | `home.visao_conta.saldo` | `saldo` |
| Home | Entradas R$ 5.000,00 / Saídas R$ 5.380,00 | `home.visao_conta.entradas` / `.saidas` | `entradas`, `saidas` |
| Home | Um espaço para planejar… · Recomeçar planejamento | `home.aviso_plano`, `home.botao_recomecar` | — |
| Chat | i.ai com Alexandre · Uma conversa para o seu momento · Reiniciar | `chat.cabecalho`, `chat.botao_reiniciar` | `primeiro_nome` |
| Chat | Seu espaço de planejamento | `chat.subtitulo` | — |
| Chat | Que bom ter você aqui, Alexandre! | `bot.intro` | `primeiro_nome` |
| Chat | Arraste para explorar | `intro.dica_arraste` | — |
| Chat | Agora vamos transformar… 50-30-20… Topa o desafio…? | `bot.convite_50_30_20` | — |
| Chat | Topo o desafio | `user.topo_desafio` | — |
| Chat | Confira os compromissos de exemplo para janeiro de 2026: | `bot.confirm` | `periodo_plano` (hoje embutido no texto) |
| Chat | Assumir meus compromissos | `user.assumir` | — |
| Chat | O primeiro passo já tem nome… | `bot.card` | — |
| Card | Um novo passo merece ser lembrado. · Este card não mostra seu saldo… | `card.titulo`, `card.privacidade` | — |
| Card | JANEIRO / 2026 · Meu delivery vai sentir saudade… · Pequenas mudanças… · Qual vai ser seu próximo passo? | `card.imagem`, `card.frases` | `periodo_plano`, `frase_card` |
| Card | Salvar imagem · Baixar PNG · Gerar outra frase · Voltar ao início sem salvar a imagem | `card.botoes` | — |

O roteiro tem ainda o painel de compromissos, `bot.finish`, o composer, as respostas por
palavra-chave e a regra de reinício.

## 4. Variáveis: de onde vêm hoje e de onde devem vir

| Variável | Hoje (front) | Alvo (backend) | Cuidado |
| --- | --- | --- | --- |
| `primeiro_nome`, `genero` | inventados no front | `perfil-usuario` (nome e gênero inventados e selados no CSV da verdade) | a base BigQuery **não tem** nome nem gênero |
| `entradas`, `saidas`, `saldo` | fórmula / Maria fixa | `usuario-real` `resumo.inflow_mensal`, `outflow_mensal`, `surplus_mensal` | são **médias mensais jan-nov/2025**. O rótulo não pode continuar "Dezembro/25". |
| `periodo_saldo`, `periodo_plano` | constantes | derivados da `data_corte` (padrão 2025-12-22) | — |
| `delivery_meta`, `valor_liberado`, `reserva` | fórmulas do front | `usuario-real` `visao/categoria?categoria=Delivery` + regra de corte | a regra de corte ainda não foi decidida. Exemplo medido: o usuário 928 tem Delivery = 0 na janela, então "Limitar delivery" não faz sentido para ele. |
| `frase_card` | `data/plan.ts` | pool `card.frases` deste roteiro | concordância por `genero` |

## 5. Regras que o roteiro protege

- **Toda fala tem id único e estágio conhecido.** Toda variável citada tem fonte declarada. Sem isso,
  `carregar_roteiro()` levanta erro e a rota responde 500. O teste tem prova negativa sintética para id
  duplicado, estágio desconhecido e variável sem fonte. Em 2026-09-27 a própria validação reprovou a
  primeira versão do roteiro por `frase_card` sem fonte.
- **O card nunca leva valor monetário** (`card.privacidade`).
- **Número mostrado ao usuário vem com selo** (ver [contrato-api-frontend.md](contrato-api-frontend.md) §3).
  Se a fonte estiver indisponível, a tela mostra "indisponível", nunca zero.

## 5a. Compromissos de janeiro: subcategoria real e modelagem (2026-09-27 05:55)

O pedido do dono (05:49) foi: "[CHAVE] é a subcategoria que já existe na tabela. Os cálculos de modelagem da
informação não estão sendo usados corretamente." O front mostrava "Limitar delivery a R$ 780,00", com
`delivery` fixo e uma meta que era a da Maria escalada pela renda, sem nenhuma modelagem.

Rota: `POST /api/v1/context-agent/i-agora/plano/proposta/` com corpo `{"ref": 928 | "<uuid>", "data_corte"?}`.
A rota também aceita `GET ?ref=`. O código está em
[`services/plano_proposta.py`](../apps/context_agent_datadriven/services/plano_proposta.py) e os testes em
`tests/test_plano_proposta.py`.

**A regra `corte_seguro_ate_surplus_15`** tem sete passos:

1. O perfil T3 da janela fornece o inflow e o surplus (médias mensais de jan–nov/2025).
2. O **necessário** é `max(0, 0,15 × inflow − surplus)`, o que falta para o usuário virar Livre.
3. As candidatas são **subcategorias** (`nom_cate_micro`, com a grafia exata da tabela) das macros do grupo
   discricionário. Essencial e compromisso financeiro nunca entram.
4. A margem de corte seguro vem do estudo (C10): Nível 1 corta 100 % e Nível 2 (restaurante, cuidados,
   transporte) corta 50 %.
5. A escolha é gulosa: a maior margem vem primeiro, com `corte = min(margem, falta)`. Entram no máximo 3
   compromissos, e `meta = gasto_atual − corte`. Subcategoria sem gasto não entra.
6. Com o necessário em 0 (usuário Livre), nada é cortado e a `reserva` é `min(surplus, 20 % do inflow)`,
   o "20" da regra 50-30-20.
7. Os estados possíveis são `OK`, `LIVRE_SEM_CORTE` e `CORTE_INSUFICIENTE`. O último acontece quando as
   margens não cobrem o necessário; nesse caso a tese Vulnerável manda renegociar o compromisso financeiro.

**O texto** é "Limitar {subcategoria} a {meta} em janeiro.". Quando a meta é 0 (Nível 1 a 100 %), vira
"Pausar {subcategoria} em janeiro (economia de {corte})."

**Resultados medidos às 05:54 BRT:**

| ref | Segmento | Estado | Compromissos (gasto → corte) | Necessário / liberado |
| --- | --- | --- | --- | --- |
| 2 | Vulnerável | CORTE_INSUFICIENTE | Delivery 913,82 → 913,82 (pausar) · Vestuario e acessorios 489,61 → 489,61 · Restaurantes 239,88 → 119,94 | 4.797,85 / 1.523,37 |
| 928 | Vulnerável | CORTE_INSUFICIENTE | Moveis e decoracao 488,19 · Eletronicos 229,72 · Vestuario e acessorios 216,37 (todos pausar) | 3.286,53 / 934,28 |
| 1 | Vulnerável | CORTE_INSUFICIENTE | Vestuario e acessorios 346,89 · Compras 223,97 · Padaria 180,73 → 90,36 | 2.959,89 / 661,22 |

No usuário 928, Delivery vale 0 na janela e não é proposto. É o caso que a regra tinha de excluir.

**Apresentação (06:05 BRT, pedido do dono pelo front).** A resposta traz agora um bloco `apresentacao` com
`chave` ("subcategoria"), `linha_de_corte` (= `data_corte`), `base` (`inicio`/`fim`/`meses`, os meses completos
antes do mês do corte que têm movimento), `raciocinio` (lista de frases) e `rodape`. O rodapé diz "Com base nos
seus registros até DD/MM/AAAA…", nunca "projeção" ou "estimativa". Cada compromisso ganha também `raciocinio` e
`ate_linha_de_corte`: o gasto da subcategoria do dia 1 do mês do corte até o corte, inclusive, com selo próprio em
`selos.ate_linha_de_corte`. Esse valor fica fora da média. Se a consulta falhar, o campo vem `"NAO_MEDIDO"`, nunca 0.
Medido: a base é jan–nov/2025 para os 1.000 usuários (`primeiro_anomes` = 202501 em todos). Mesmo assim, o
backend a calcula por usuário. No ref 1, Vestuario tem 654,73 até 22/12 contra média de 346,89/mês.

**Limites.** A essencialidade vem da palavra-chave na **macro**, como no estudo. Por isso Pets e Assinaturas
são Nível 1 e cortam 100 %. A escolha dos 3 compromissos não foi validada com o dono.

## 6. Próximos passos (não feitos)

1. O front passa a ler as falas de `controle-conversa/` e a reconhecer as bolhas por id, não por texto.
2. Uma rota `controle-conversa/<ref>/` devolve as falas já preenchidas, com as variáveis da §4 e o selo de
   cada número.
3. Decidir a regra de compromissos com dado real: qual categoria discricionária propor e qual meta de corte usar.
