# Interações front ↔ back: regras de conversa e produção de interações

Documento **conjunto**. O front é `frontend-agent-conversacional` (mobile-front-agente). O back é este
repositório, onde duas sessões dividem as rotas. Cada seção diz quem é o dono. Uma seção marcada
**A PREENCHER** ainda não foi escrita pelo dono dela.

| Seção | Dono |
| --- | --- |
| 1. Princípios | conjunto |
| 2. Mapa por etapa (telas) | front |
| 3. Catálogo de chamadas | back-25 (usuário real, proposta, controle) · back-32 (perfil, conversas) |
| 4. Fluxos de prompt | back-32 |
| 5. Texto fixo vs gerado | back-25 |
| 6. Selos e NAO_MEDIDO | back-25 |
| 7. Processo de mudança | conjunto |

## 1. Princípios

- O front nunca chama o modelo. O caminho é sempre front → Django → Gemini, e só o Django tem a chave.
- Todo número mostrado vem de uma rota, com **selo** (fonte, hora BRT, job). Nenhum número é inventado no navegador.
  > **Violação conhecida (front `2835401`, 2026-09-27).** O cartão "Visão da conta" do Início (saldo, entradas e
  > saídas de dezembro) ainda mostra valores sintéticos locais (`personService.calculatePerson`; Maria: −R$ 380,00),
  > **sem selo e sem rótulo**. A proposta também cai em valores locais quando a rota falha, mas aí com o rótulo
  > "Valores de exemplo: backend indisponível (NAO_MEDIDO)". Para fechar a violação, o dono tem de decidir que número
  > o cartão mostra: `saldo-mes.saldo` (dezembro até 22/12) ou `media_mensal`. Até lá o princípio vale para a proposta
  > e para a mensagem de apoio, não para o cartão.
- Se uma fonte falhar, a tela diz "indisponível" ou `NAO_MEDIDO`. Nunca mostra zero no lugar do valor.
- Toda fala que a pessoa vê tem um id no controle da conversa ([controle-da-conversa.md](controle-da-conversa.md)).
  > **Pendente.** As falas do front vivem em `src/data/conversation.ts` (BOT/INVITE_MESSAGE/USER), ainda não têm id
  > e não vêm de `controle-conversa/`. As 3 falas de apoio a negativados já estão registradas no roteiro 2026-09-27.2
  > (`bot.apoio_negativado`, `home.aviso_negativado`, `bot.humano_negativado`). O front liga `controle-conversa/` quando o dono pedir.
- O card compartilhável nunca leva valor monetário.

## 2. Mapa de interações por tela e etapa (front)

Texto do front, versão de 2026-09-27 06:30 BRT. Fonte: mobile-front-agente, commit `2835401`.

As telas seguem a ordem Início → Conversa → Acompanhe, e a Conversa passa pelas etapas intro → invite → confirm →
card → finish. As etapas ficam em `src/hooks/usePlanConversation.ts` e os botões em
`src/components/chat/stages/StageActions.tsx`.

| # | Momento / botão (data-testid) | Chamada | Espera | Sucesso | Erro / NAO_MEDIDO |
|---|---|---|---|---|---|
| 2.1 | Abrir o Início / trocar de pessoa | `GET usuario-real/<indice>/saldo-mes/` (25), uma vez por pessoa, timeout 20 s | tela desenhada com o saldo local | guarda `person.saldoMedido`; negativado = `negativado_na_media` | `saldoMedido=null`: decide pelo saldo exibido |
| 2.2 | Abrir a conversa (`button-open-iai`, balão, Conferir, Planejar, "Conversar com i.ai") | hoje é local: nova pessoa com `id` = número de aberturas e `indice = id+1`. Futuro: `POST perfil-usuario/definir/` (32), que devolve `sessao_id` + `usuario` | — | — | futuro: 404 em qualquer rota da 32 → chama `definir/` de novo |
| 2.3 | Intro (1.ª interação) | nenhuma | — | negativado: bolha de apoio (juros altos, unir dívidas, falar com humano) logo depois de "Que bom ter você aqui" | — |
| 2.4 | `button-open-iagora` (intro → invite) | nenhuma; texto fixo INVITE_MESSAGE, sem "projetar" | "digitando" 650 ms | etapa `invite` | — |
| 2.5 | `button-start-plan` "Topo o desafio" (invite → confirm) | `POST i-agora/plano/proposta/ {ref: indice}` (25), timeout 10 s | "digitando" durante toda a chamada; a 1.ª chamada fria leva ~4 s | painel com `compromissos[].texto` + `raciocinio` + `ate_linha_de_corte`, `totais.valor_liberado/reserva`, `apresentacao.raciocinio[]` e `apresentacao.rodape`; CORTE_INSUFICIENTE mostra a falta; LIVRE_SEM_CORTE mostra "nenhum corte" | `proposal=null`: valores locais com o rótulo "Valores de exemplo: backend indisponível (NAO_MEDIDO)" |
| 2.6 | `button-assume-commitments` (confirm → card) | hoje é local (copia draft+proposta para `confirmed`). Proposta: `POST i-agora/plano/confirmar/` com Idempotency-Key (**rota não existe**) | 650 ms | card PNG, sem valores pessoais | — |
| 2.7 | `button-adjust-values` | nenhuma: recusa com texto fixo | 650 ms | — | — |
| 2.8 | `button-save-image` / `button-download-image` / `button-change-phrase` | nenhuma: PNG gerado no navegador | — | compartilhar/baixar | toast de erro |
| 2.9 | Texto livre (`button-send-message`) | hoje é local (`conversationService.replyTo`). Futuro: `conversas/sessao/` + `conversas/mensagens/` (32), com cookie + X-CSRFToken + `X-Sessao-Id`, nunca no corpo | "digitando" | resposta do modelo; `dados.selo` é mostrado | 503 (modelo/guard/429): "indisponível", nunca número; 404: `definir/` |
| 2.10 | "humano" / "atendimento" no texto | local | — | negativado: encaminha ao atendimento do app; senão, "não consigo iniciar atendimento" | — |
| 2.11 | Reiniciar / Recomeçar | local (mesma pessoa, apaga o plano) | — | — | — |

Regras do front que valem para todas as linhas:
- **R-F1.** Um número só aparece com selo (regra, fonte, medido_em) ou com o rótulo NAO_MEDIDO. Nunca zero no
  lugar de NAO_MEDIDO.
- **R-F2.** Janeiro não é projetado: o texto diz "limites para janeiro calculados sobre os registros até
  <linha de corte>".
- **R-F3.** O front nunca chama o modelo nem vê a chave.
- **R-F4.** Enquanto uma chamada corre, os botões da etapa ficam escondidos (o "digitando" está visível), o que
  impede o duplo clique.
- **R-F5.** Uma resposta que chega depois de trocar de pessoa é descartada (o front compara `person.id`).
- **R-F6.** O estado local em localStorage (`i-agora-maria-janeiro-2026-v4`, `i-agora-pessoas-v1`) é só cache;
  a verdade é o backend.

## 3. Catálogo de chamadas

Base: `/api/v1/context-agent/`. Porta local 8001, com o proxy do Vite apontando para `DJANGO_URL`.

### 3.1 Rotas da back-25 (identificam o usuário por `ref` = índice ou UUID; não usam `sessao_id`)

| Rota | Para quê | Campos que o front usa |
| --- | --- | --- |
| `GET usuario-real/<ref>/` | perfil T3 e as cinco visões | `resumo.*`, `selo` |
| `GET usuario-real/<ref>/saldo-mes/` | saldo do mês do corte e média mensal | `negativado_na_media`, `media_mensal.surplus_mensal`, `saldo`, `selo` |
| `POST i-agora/plano/proposta/` `{"ref"}` | compromissos de janeiro pela modelagem | `compromissos[].texto/raciocinio/ate_linha_de_corte`, `apresentacao.*`, `totais` |
| `GET controle-conversa/[?estagio=]` | roteiro de todas as falas | `falas[].id/texto/variaveis` |

Erros: `400` para ref ou data inválida, `404` para usuário inexistente, `422` para pedido fora do catálogo,
`503` com `estado: OFF` quando a fonte está desligada e `503` com `estado: NAO_MEDIDO` quando o BigQuery falha.
Os campos completos estão em [contrato-api-frontend.md](contrato-api-frontend.md).

### 3.2 Rotas da back-32 (usam `sessao_id` no header `X-Sessao-Id`)

Prefixo `/api/v1/context-agent/`. Contrato detalhado: `backend-agente-conversacional/docs/contrato-api-frontend.md`
§5.1, §5.2 e §5.3. Estado às 06:27 BRT: **estável**, exceto onde diz "em construção".
**Ainda fora deste git** (medido às 06:35 BRT): o código destas rotas e as seções §5.1–§5.3 do contrato estão só na
pasta de trabalho do backend. O que está em `origin/main` são as rotas da back-25.

| Rota | Identificação | Resposta 2xx | Erros |
| --- | --- | --- | --- |
| `POST perfil-usuario/definir/` `{"usuario": "<indice\|uuid>"}` | nenhuma: é a chamada que **abre** a sessão | 201 `{sessao_id, expira_em_segundos, usuario:{codigo, pessoa, genero, indice}}` | 400 corpo · 404 usuário · 503 `NAO_MEDIDO` (sem o CSV da verdade) |
| `POST perfil-usuario/pergunta/` `{sessao_id, pergunta}` | `sessao_id` no corpo | 200 `{resposta, usuario, intencao, modelo, guard:{estado:"APROVADO"}}` | 404 sessão · 502 `guard.REPROVADO` · 503 modelo |
| `GET conversas/sessao/?sessao_id=` | `X-Sessao-Id` ou query | 200 envelope 1.0 + `usuario`; grava os cookies `csrftoken` e `conversa_sessao` (4 h) | 404 sessão · 503 |
| `POST conversas/mensagens/` | cookie + `X-CSRFToken` (+ `X-Sessao-Id` opcional, que vale mais que o cookie). **O `sessao_id` nunca vai no corpo**, porque o schema é estrito. | 200 envelope 1.0 + `dados:{estado: MEDIDO\|NAO_MEDIDO\|OFF, selo}` | 400 schema · 403 CSRF · 404 sessão · 409 `client_message_id` repetido · 429 limite · 503 modelo ou guard |
| `POST conversas/interacao/` `{etapa, escolha?}` | `X-Sessao-Id` | **em construção** (contrato §5.3); o front não liga até a back-32 avisar | — |

Identidade: `usuario.codigo` = `id_usuario` da base; `usuario.pessoa` e `usuario.genero` vêm do CSV da verdade
(nome e gênero **sorteados**, com semente fixa; índice 1 = Maria, F). O front usa `usuario.indice` como `ref`
nas rotas da back-25. As sessões ficam na memória do processo: um reinício do servidor dá 404 e o front chama
`definir/` de novo.

## 4. Fluxos de prompt

Caminho único: **front → Django → Gemini**. O front nunca chama o modelo. A chave `API_KEY_SECRECT` só é lida no
servidor (`desafio_itau/segredos.py`) e vai no header `x-goog-api-key`, nunca no URL. Os nomes dos modelos têm
uma fonte única, `desafio_itau/modelos_llm.py`: `gemini-3.5-flash-lite` é o principal e `gemini-flash-latest`
fica de reserva. Um modelo fora desse ficheiro é recusado.

| Chamada | Entra no prompt | Guards (resposta que reprova não sai) | Se o modelo falhar |
| --- | --- | --- | --- |
| `perfil-usuario/pergunta/` | só a identidade: pessoa, código e gênero | "quem sou eu"/nome/código têm de trazer o nome **e** o código exatos | tenta o próximo modelo; se todos reprovarem, 502; se nenhum responder, 503 |
| `conversas/mensagens/` | identidade + dados medidos do `usuario-real` com selo (perfil T3, entradas, saídas, dívidas, recorrências) + base normativa (BCB Res. Conjunta 8/2023) + política institucional | identidade; valores citados = medidos; dados sensíveis (CPF, cartão; o código do próprio titular é permitido); fairness; citações só de `bcb.gov.br`/`itau.com.br` | 503 no envelope. Sem BigQuery, `dados.estado = NAO_MEDIDO`, sem números. Nunca aparece zero. |
| `conversas/interacao/` `{etapa, escolha?, mensagem?}` + `X-Sessao-Id` | esqueleto determinístico de `apps/conversas/fluxos_comportamento.json` (v2026-09-27.1: 16 fluxos, T3 × SOBROU/FALTOU/EQUILIBRIO/NAO_MEDIDO, escolhidos por código; o modelo só redige) + dados medidos com selo + BCB 8/2023 + 50-30-20 | números = medidos; situação coerente com o sinal; nome/gênero; política; 50-30-20 com período; tom T3; ortografia pt-BR ("voce", "orcamento" e "mes" reprovam); alucinação: data, categoria, produto ou normativo fora do bloco de contexto reprova (regras de `docs/context_scoring.md` §1, `system.liquid`, `knowledge/indice.json` e `rules.valid_evidence`) | próximo modelo; depois, texto do roteiro rotulado `origem_resposta: "roteiro"` |

Cenários fixos em `mensagem` (back-32, `conversas/interacao/` fechada às 06:39 BRT com 240 testes OK):
- **Inclinação de gasto:** compara os últimos 3 meses com a média da janela. Só entra com variação ≥ 15 % e
  diferença ≥ R$ 30/mês, apenas em desejos e Mercado. Sem dado, não há frase.
- **Consolidação de dívida com encaminhamento a um atendente humano:** dispara quando empréstimos + juros
  somam ≥ 10 % da entrada ou há multa por atraso, e o perfil é Vulnerável ou FALTOU. A frase de encaminhamento é
  fixa e anexada pelo servidor, sem taxa. **Ainda não existe rota de atendimento humano**: o encaminhamento é só
  texto.
- **Fora de contexto:** texto fixo, sem modelo.

Cada resposta é avaliada no momento em que é gerada e registrada em `relatorios/avaliacoes/<data>.jsonl`. O
resumo sai em `GET conversas/avaliacoes/resumo/`. Medido pela back-32 em 2026-09-27: 49 respostas, 100 %
aprovadas, p50 1125 ms e p95 1498 ms. Contrato: §5.3, que também está fora deste git.

Fora do contexto financeiro a resposta é **fixa**, sem modelo. A redação ainda espera a confirmação do dono;
o texto provisório é "Não faço ideia, sabia? Aí é que eu não sei.".

Fato medido para esta seção: `gemini-3.8-flash` respondeu **429** às 06:12 BRT de 2026-09-27. A chave está no
plano gratuito, com quota de 20 pedidos/dia por modelo (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`).
O modelo em uso é `gemini-3.5-flash-lite`.

## 5. Texto fixo vs gerado

| Tipo | Origem | Exemplo |
| --- | --- | --- |
| Fixo, com variáveis | `roteiro.json` (`controle-conversa/`) | `bot.intro` "Que bom ter você aqui, {primeiro_nome}!" |
| Gerado por regra, sem LLM | `plano/proposta` | "Pausar Delivery em janeiro (economia de R$ 913,82)." |
| Gerado por modelo | `conversas/` (back-32) | resposta a texto livre |

Uma fala nova só entra no front depois de entrar no roteiro. A bolha é reconhecida pelo **id**, não pela
igualdade do texto.

## 6. Selos, NAO_MEDIDO e decisões de exibição

- **Mensagem de apoio a quem está negativado.** Decisão do dono de 2026-09-27 06:22 BRT, repassada pelo front:
  a mensagem usa o saldo **completo**, ou seja, a média dos meses completos antes do mês do corte
  (`saldo-mes.negativado_na_media`, isto é, `media_mensal.surplus_mensal < 0`). Se a rota responder 503, o front
  decide pelo saldo exibido, que hoje é sintético (ver a violação conhecida no §1). Isso é portanto uma contingência
  de demo, não uma medição. Exemplo do ref 1: média de −R$ 1.729,62 (negativado) e dezembro até 22/12 de
  +R$ 1.072,11. A decisão segue a média.
- A proposta mostra "Com base nos seus registros até DD/MM/AAAA". Nunca "projeção" nem "estimativa".
- `ate_linha_de_corte` fica fora da média. Quando a consulta falha, o campo vem `"NAO_MEDIDO"`, e 0 só aparece
  quando foi medido.

## 7. Processo de mudança

- Uma mudança de campo em rota muda também este documento e o contrato, no mesmo commit.
- Quem muda uma rota avisa o front antes de o front ligar a rota.
- Nenhuma decisão de produto (limiar, qual saldo, regra de corte) é tomada por uma sessão sozinha: ela é
  registrada aqui com a data e com quem decidiu.
