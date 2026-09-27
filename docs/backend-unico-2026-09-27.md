# Backend único e correções de integração com o front — 2026-09-27

Sessão backend-21 (Claude Code), 10:58–12:00 BRT. Objetivo do dono: um só backend (`Nova pasta/backend`)
servindo o front (Vite :3000, proxy `/api/v1` -> `127.0.0.1:8000`), com todas as integrações e o Gemini a responder.

## 1. O que estava errado

| Sintoma no front | Causa medida | Correção |
|---|---|---|
| `GET conversas/sessao/` 502 no proxy da :3000 | Nada ouvindo na :8000 (e, noutro momento, dois processos na mesma porta: este backend e o `agent_backend` do `Frontend/`). | Um só `runserver 127.0.0.1:8000` deste backend; o `agent_backend` foi derrubado. `.venv` criado (o Django não estava no Python global). |
| Resposta "Demonstração local: esta resposta é fixa…" | Vinha do `agent_backend`, que corria em modo `demo` (nunca chama o Gemini). | Este backend corre em `CONVERSAS['MODO']='demo_live'` (padrão). |
| Gemini sem credencial | `desafio_itau/segredos.py` procura `.secrets` em `Nova pasta/.secrets` ou `Nova pasta/frontend-agent-conversacional/.secrets`; nenhum existia. | `.secrets` (chave `API_KEY_SECRECT`) colocado em `Nova pasta/.secrets`, fora do repositório (e `.secrets` está no `.gitignore`). A chave é lida a cada chamada, sem cache. |
| 503 intermitente em `conversas/mensagens` com o Gemini respondendo | O guard de números (`numeros_sem_fonte`) lia `R$ 4359.90` como `R$ 4359`: o valor não batia com o fato `4359.90` e a resposta era barrada (`deterministic_reject`). Com `R$ 4.359,90` passava — por isso era intermitente. | `apps/context_agent_datadriven/pastas_raiz/estudos/i_agora/guard.py`: ponto seguido de 1–2 dígitos é decimal; com 3 dígitos segue milhar. Teste com prova negativa em `tests/test_t3_guard_i_agora.py`. |
| 503 determinístico em perguntas de "sobras" de titular com fluxo negativo | Fato `cash_flow=-1729.62`; o Gemini escreve "fluxo negativo de R$ 1.729,62" e o guard só comparava a magnitude com a fonte com sinal. Diagnóstico da sessão Frontend (241cb976), reproduzido às 11:34. | `apps/conversas/estado.py`: fonte negativa sustenta a magnitude escrita só se a mesma frase marca o sinal (`-`/`−` colado, negativo/déficit/falta/rombo/a menos, até 60 caracteres antes); palavra positiva entre o marcador e o número anula. `tests/test_numeros_sinal_negativo.py`: 3 casos reais + 5 provas negativas (sobra inventada, sinal invertido, marcador noutra frase). |
| `generate` estoura 15 s e o reserva também cai em 429 | `MODELO_CONTINGENCIA` era igual ao principal (`gemini-3.5-flash-lite`), então o reserva ia para `gemini-flash-latest`, que devolveu 429 em 4/4 sondas (11:38-11:41). | `desafio_itau/modelos_llm.py`: `MODELO_CONTINGENCIA = "gemini-3.5-flash"` (cota própria). Ajuda às vezes; não garante resposta com o Gemini degradado. `MODELOS_GOOGLE` não foi tocado. |
| `i-agora/perfil`, `i-agora/plano`, `sessao/abertura`, `plano/confirmar` 404 (front cai em modo só-chat) | Essas rotas só existiam no `agent_backend`. | Portadas para `apps/i_agora/` (commit b95cf2a): perfil, sessao/abertura, plano GET/PATCH/DELETE, plano/proposta POST/DELETE, plano/rascunho, plano/confirmar, acompanhamento. |
| `conversas/sessao/` 404 sem `definir/` antes | O bootstrap exigia sessão já definida. | Sem sessão, sorteia um titular entre os 1.000 de `data/usuarios_verdade.csv` (`SystemRandom`). |

## 2. Regra do titular (pedido do dono)

- Quando o front pede sem sessão, o titular é **sorteado** entre os 1.000 usuários.
- Toda a interação — `conversas/*` (Gemini) e `i-agora/*` (perfil, plano, proposta, confirmar) — fica com **esse mesmo titular**.
- Só `POST i-agora/sessao/abertura/ {"next": true}` troca o titular, sempre para outro diferente do atual, e a troca vale em todas as rotas.
- O caminho do front publicado continua válido: `POST perfil-usuario/definir/ {"usuario": "<UUID>"}` -> `GET conversas/sessao/?sessao_id=` -> cabeçalho `X-Sessao-Id`.

## 3. Conflito em `i-agora/plano/proposta/`

A mesma URL atende os dois contratos pelo corpo: `POST` com `clientRequestId` e `DELETE` seguem o contrato do front
(sessão + CSRF, devolve `state`; sem caso preparado dá 409). `GET` e `POST` sem `clientRequestId` continuam na
`PlanoPropostaAPI` anterior.

## 4. Verificação

- Suíte: `.venv/Scripts/python -m unittest discover -s tests` — **588 testes OK** (skipped=1, expected failures=22),
  11:50 BRT, com todas as correções deste documento.
- Fluxo real pela :3000 (proxy Vite, cookies, CSRF, BigQuery e Gemini reais), 11:44-11:48 BRT:

| Passo | Status |
|---|---|
| `GET conversas/sessao/` sem sessão | 200, titular sorteado |
| `GET i-agora/perfil/` | 200, mesmo titular |
| `GET i-agora/plano/` | 200 |
| `POST i-agora/sessao/abertura/ {next:false}` | 201 |
| `POST conversas/mensagens/` (Gemini) | **200** — "Olá, Bruno (código 08a70787…). … suas saídas médias mensais foram de R$ 5.128,33." (input_guard 906 ms, generate 1969 ms, output_guard 2235 ms) |
| `POST i-agora/plano/proposta/` sem caso preparado | 409 (esperado: o caso nasce da conversa) |
| `GET i-agora/acompanhamento/` sem plano confirmado | 404 |
| `POST i-agora/sessao/abertura/ {next:true}` | 201, outro titular; `i-agora/perfil` passa a devolvê-lo |
| B: `definir/ {usuario:UUID}` -> `sessao/?sessao_id` -> `i-agora/perfil` com `X-Sessao-Id` | 201 -> 200 -> 200, titular do UUID |
| `POST conversas/mensagens/` em sequência rápida | 503 com `erro_api.codigo=429` (cota do provedor, §5) |

O caminho proposta -> confirmar -> PATCH -> DELETE foi validado pelo test client (com o caso preparado no servidor)
e está coberto por `tests/test_i_agora_*.py`.

### 4.1 Pendências do §5 (backend-22, 12:24-12:45 BRT)

**Medido** (fonte: sonda direta `generateContent` com o corpo do `input_guard`, métricas de `GET conversas/status/`
num `runserver` próprio em :8013, e o ledger `relatorios/avaliacoes/2026-09-27.jsonl`):

| O quê | Valor | Fonte · hora BRT |
|---|---|---|
| Cota diária `gemini-3.5-flash-lite` | 429 `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, limite 500/dia, `retryDelay` 35 s | sonda · 12:29 |
| Cota diária `gemini-3.5-flash` (contingência) | 429 idem, limite 20/dia | sonda · 12:29 |
| Cota diária `gemini-flash-latest` (serve `gemini-3.8-flash`) | 429 idem, limite 20/dia, `retryDelay` 52 s | sonda · 12:31 |
| `gemini-3.5-flash` antes do 429 | parado até o timeout: 15109, 15109, 15188 ms (3/3, timeout 15 s); 10079 ms com o timeout novo de 10 s | status/métricas · 12:26-12:28 e 12:34 |
| Guards com sucesso (conversas) | 906, 937, 2235 ms | §4 (11:44) e diagnóstico · 12:26 |
| `generate` com sucesso (conversas) | 1969 ms (n=1) | §4 · 11:44 |
| `gemini-3.5-flash-lite`, rota interacao/ | n=34, p50 1250, p95 1516, máx 1812 ms | ledger de avaliações · 06:10-10:xx |
| `generate` com sucesso acima de 2,3 s | NAO_MEDIDO (nenhuma amostra) | — |

**Mudou** (`apps/conversas/gateway.py`, `apps/conversas/views.py`):

- Timeout por etapa (`TIMEOUT_POR_ETAPA`): `input_guard` e `output_guard` 10 s (4,5x o máximo medido), `generate` 15 s
  (sem amostra que justifique subir). Caminho feliz no pior caso: 10 + 15 + 10 = 35 s < 45 s do serviço < 50 s do
  front. Com nova chamada o teto de 45 s (`ConversationService.timeout`) corta antes dos 50 s do front. Efeito medido:
  o 503 da mensagem com o modelo de contingência parado saiu em 10,6 s (antes 15,5 s).
- Cota diária: o 429 do provedor passa a carregar o tipo de cota lido **só** de `details[].violations[].quotaId`
  (`dia`/`minuto`; nada do corpo vai para a exceção). Com `PerDay`, o modelo fica fora por `PAUSA_COTA_DIARIA_S` = 900 s:
  o gateway não o chama (métrica `pulado_cota_diaria`, 0 ms, sem gastar o orçamento do processo) e segue o tratamento do
  429 (outro modelo, no máximo uma nova chamada). Passada a pausa, UMA chamada real volta a sondar. A política
  `erros_api-v1.json` não mudou. Medido na :8013: 1ª mensagem 2 chamadas (10,6 s), 2ª 1 chamada (0,4 s), 3ª e 4ª
  **0 chamadas** (0,0 s), todas 503 com `erro_api.codigo=429`, `acao_cliente=aguardar_e_tentar_novamente`.
- `GET conversas/status/` ganhou `cota_diaria_esgotada` ({modelo: segundos até a sonda}) e
  `limites.timeout_por_etapa_s` (aditivos).

**Testes:** `tests/test_cota_diaria_e_timeout.py` (11, com provas negativas: 429 por minuto/sem tipo não pausa, "PerDay"
fora do `quotaId` não conta) e `tests/test_compromisso_caminho_completo.py` (3: quatro turnos, categoria delivery com
"R$ 1.522,90" x fato `1522.9`, proposta -> confirmar -> PATCH -> acompanhamento; provas negativas: valor que a pessoa não
disse e alvo acima do observado não viram caso). Suíte: **602 OK** (skipped=1, expected failures=22), 12:45 BRT.

**Fluxo HTTP na :8013 (12:34-12:36 BRT, código novo, Gemini real sem cota):** `GET conversas/sessao/` 200 ->
`GET i-agora/perfil/` 200 -> `GET i-agora/plano/` 200 -> 4x `POST conversas/mensagens/` 503 (504 na 1ª, 429 nas
seguintes) -> `POST i-agora/plano/proposta/ {clientRequestId}` 409 -> `POST i-agora/plano/confirmar/` 409 ->
`GET i-agora/acompanhamento/` 404. O caso não foi preparado porque nenhuma mensagem chegou ao `generate`.

### 4.2 Router por etapa/erro, códigos de erro e verificação real (backend-22, 12:38-13:03 BRT)

**Mudou:** `apps/conversas/roteador.py` (novo), `desafio_itau/politica/cotas-gemini-v1.json` (novo, dados do router),
`desafio_itau/politica/erros_api-v1.json` 1.2.0 (tabela `tipos`), `erros_api.py`, `apps/conversas/{gateway,service,views}.py`,
`apps/i_agora/{views,store}.py`, `desafio_itau/saude.py` (`GET /api/health/`).

**Defeito achado na verificação real e corrigido:** o `gemini-3.1-flash-lite` devolve `policy_version: "2026-09-27"` no
guard (ignora o `const` do schema) — 4/4 `input_guard` reprovados na :8013 às 12:55-12:56. `gateway.decisao_guard` passa a
carimbar `policy_version` (é do servidor); `decision`/`reason_codes`/`constraints` continuam estritos, campo extra continua
proibido (prova negativa em `tests/test_roteador_e_erros_tipo.py`). O `generate` do mesmo modelo valida sem ajuste
(amostra real 13:03).

**Conversa real na :8013 (13:01:38-13:02:02 BRT, `runserver` próprio, parado depois):** `POST conversas/mensagens/`
**200** em 24,1 s, `status=needs_clarification`. Métricas de `GET conversas/status/`:

| etapa | modelo | resultado | ms | nova chamada |
|---|---|---|---|---|
| input_guard | gemini-3.1-flash-lite | complete (`modelVersion` gemini-3.1-flash-lite) | 5312 | não |
| generate | gemini-3.5-flash-lite | 429 cota diária | 515 | não |
| generate | **gemini-3.1-flash-lite** | complete | 2719 | sim (router, 429 -> próximo com cota) |
| output_guard | gemini-3.1-flash-lite | timeout (10 s) | 10078 | não |
| output_guard | **gemini-3.6-flash** | complete | 1844 | sim (router, 504 -> o mais rápido) |

`roteador.ultimo_modelo_por_etapa` = `{input_guard: gemini-3.1-flash-lite, generate: gemini-3.1-flash-lite,
output_guard: gemini-3.6-flash}`; resfriamentos: `gemini-3.5-flash-lite` 885 s (cota_dia), `gemini-3.1-flash-lite` 58 s
(timeout). Os 24,1 s ficam abaixo dos 45 s do serviço e dos 50 s do front.

**Caminho de compromisso (12:58-13:00 BRT):** 3 falas -> 3x 503 `provedor_indisponivel`. Os guards já passavam
(1969/1515/1297 ms), mas o `generate` reprovava em validação por um carimbo de `schema_version` que eu tinha posto por
engano no `AgentDraftV1` (campo que ele não tem); retirado às 13:03, e a conversa real acima passou. Depois: proposta
409 `sem_proposta`, confirmar 409, acompanhamento 404 `sem_objetivo_confirmado`. **Caminho completo com Gemini real: NÃO
verificado** — o orçamento de chamadas da tarefa (≤40) acabou (≈41 usadas); ver §5.

**Testes:** `tests/test_roteador_e_erros_tipo.py` (22: ordem dos dados e prova negativa de modelo não apto; 429 no 1º
-> responde o 2º; resfriamento com `retryDelay` respeitado sem chamada; volta ao 1º depois do resfriamento; 400 não troca
nem resfria; timeout -> o mais rápido; no máximo 1 nova chamada; todos sem cota -> 0 chamadas e 429; teto de RPM do
painel desvia; HTTP/tipo 429/504/503/`resposta_reprovada_validacao`; `Retry-After`; todos os tipos com `codigo` inteiro e
`tipo` não nulo; erros de conversas e i-agora; `/api/health/`; status expõe o router). Suíte: **624 OK** (skipped=1,
expected failures=22), 13:03 BRT.

### 4.3 Erro real do dono depois da abertura (backend-22, 13:09-13:22 BRT)

**Sintoma (:3000 -> :8000, 13:09):** `POST i-agora/sessao/abertura/` 201 ("…despesa pontual importante ou são gastos que
costumam se repetir?") -> `POST conversas/mensagens/` "São gastos que costumam se repetir, quase toda semana." -> 503
`provedor_indisponivel`/NAO_CLASSIFICADO em 16,4 s; `ultimo_modelo_por_etapa` sem o `generate`.

**Causas medidas** (reprodução com o Gemini real, 12 chamadas no total):

1. `maxOutputTokens` inclui o pensamento. `gemini-3.1-flash-lite`, output_guard: 490 tokens de pensamento no teto de
   512 -> `finishReason MAX_TOKENS`, JSON cortado em `{"decision": "release",` (13:15). O generate já usava 1026 + 260
   do teto de 1800. Correção: `MAX_TOKENS_GUARD` 2048, `MAX_TOKENS_GENERATE` 4096.
2. Saída inválida do modelo (não-STOP, JSON, schema) parava o router: exceção sem status, sem nova chamada. Correção:
   `RespostaInvalida` segue para o próximo modelo da ordem ainda não tentado, sem gastar a nova chamada da política,
   dentro do prazo do turno (`PRAZO_TURNO`, 45 s); se todos falham, HTTP 503 `resposta_modelo_invalida` (linha 503,
   nunca NAO_CLASSIFICADO) — erros_api 1.3.0.
3. A pergunta da abertura não chegava ao modelo (history vazio). Correção: `context.abertura {fase, pergunta, foco}`
   em `conversation_context` e uma linha no prompt de sistema para seguir esse fio.
4. `valid_evidence` comparava texto: o modelo citou `"34.60"` para o fato `"34.6"` (str de float) e a resposta certa
   saiu 503 `resposta_reprovada_validacao` (13:19). Correção: igualdade numérica exata (Decimal) só entre dois números
   em ponto decimal; "34.61", "R$ 34,60", "3.46e1" continuam reprovados.
5. Processo recém-iniciado: guard 3.1-flash-lite em timeout -> o "mais rápido" era o 3.5-flash-lite sem cota do dia ->
   429 em 360 ms gastava a nova chamada -> front recebeu 429 (13:20). Correção: 429 de cota **diária** não gasta a
   nova chamada (recusa sem processar, a mesma informação do resfriamento).
6. Status: toda etapa aparece em `ultimo_modelo_por_etapa` (null = sem resposta válida); novos
   `ultima_tentativa_por_etapa {modelo, resultado}` e `proximo_por_etapa`; métricas com `error_type`,
   `motivo_invalida`, `http_status`.

**Verificado ao vivo na :8013 (13:21:43-13:22:21 BRT, runserver próprio recém-iniciado, parado depois):** sessao 200 ->
perfil 200 -> abertura 201 ("…R$ 163,78 no período… ou são gastos que costumam se repetir?") -> mensagem do dono
**200 em 31,9 s**, `needs_clarification`: "Compreendido, Daniel. Como são gastos que ocorrem quase toda semana, eles
representam uma parcela constante do seu orçamento. Em dezembro de 2025, você utilizou R$ 163,78 com delivery e
refeições fora. Gostaria de estabelecer um objetivo de gasto menor…". Por etapa: input_guard 3.1-flash-lite 1312 ms;
generate 3.5-flash-lite 429 (515 ms) -> 3.1-flash-lite 14938 ms (9786 tokens); output_guard 3.1-flash-lite timeout
10094 ms -> **3.6-flash** 1640 ms. Testes: `tests/test_resposta_invalida_e_abertura.py` (18). Suíte **642 OK**
(skipped=1, expected failures=22), 13:21 BRT. Rotação: [`rotacao-modelos-gemini.md`](rotacao-modelos-gemini.md).

## Códigos de erro para o front (erros_api 1.3.0)

Todo erro de `conversas/*` e `i-agora/*` sai com `erro_api.codigo` **numérico** e `erro_api.tipo` **estável**, nunca
null. O HTTP da resposta é o do tipo; 429/503/504 com espera levam `Retry-After` (segundos). `repetir_mesmo_pedido`
continua `false` em todas as linhas. Fonte: `desafio_itau/politica/erros_api-v1.json` 1.2.0 (1.1.0 arquivada em
`desafio_itau/politica/archive/2026-09-27/`).

| tipo | codigo | HTTP | origem | acao_cliente | tentar_novamente_em_s |
|---|---|---|---|---|---|
| cota_provedor | 429 | 429 | provedor | aguardar_e_tentar_novamente | 30 |
| timeout_provedor | 504 | 504 | provedor | aguardar_ou_encaminhar | 15 |
| provedor_indisponivel | 503 (ou o status real 5xx) | 503 | provedor | aguardar_ou_encaminhar | 10 |
| resposta_modelo_invalida (1.3.0) | 503 | 503 | provedor | aguardar_ou_encaminhar | 10 |
| resposta_reprovada_validacao | 503 | 503 | api | aguardar_ou_encaminhar | 10 |
| sessao_ausente | 401 | 401 (404 em conversas/, contrato anterior) | api | reiniciar_sessao | — |
| csrf | 403 | 403 | api | reiniciar_sessao | — |
| acao_indisponivel | 403 | 403 | api | nao_repetir | — |
| schema | 400 | 400 | api | reformular | — |
| metodo_nao_permitido | 405 | 405 | api | nao_repetir | — |
| conflito_idempotencia | 409 | 409 | api | enviar_como_nova | — |
| plano_desatualizado | 409 | 409 | api | nao_repetir | — |
| sem_proposta | 409 | 409 | api | nao_repetir | — |
| rate_limit_usuario | 429 | 429 | api | aguardar_e_tentar_novamente | 30 |
| nao_encontrado | 404 | 404 | api | reiniciar_sessao | — |
| sem_objetivo_confirmado | 404 | 404 | api | nao_repetir | — |
| fonte_indisponivel | 503 | 503 | api | aguardar_ou_encaminhar | 10 |
| interno | 503 | 503 | api | aguardar_ou_encaminhar | 10 |

Mudança de contrato: falha do provedor deixa de sair sempre em HTTP 503 — cota 429, timeout 504. O front
(`Frontend/src/services/backend.ts`) já trata `!r.ok`, lê `erro_api` por `parseErroApi` (ignora `tipo`, campo aditivo)
e `Retry-After` por `parseRetryAfter`; `telaDeErro` já trata 429/503/504 como "ocupado". O proxy do Vite
(`'/api/v1'` -> Django) repassa status e cabeçalhos. `Frontend/` não foi alterado. `GET /api/health/` = alias do
`/healthz` (`{"status":"ok"}`); está fora de `/api/v1`, logo fora do proxy do Vite.

## Limites do provedor

Fonte: painel AI Studio "Limites de taxa por modelo", colado pelo dono às 12:39 BRT — **não medido pelo backend** (a API
não expõe cota restante). IDs confirmados por `GET v1beta/models` às 12:40 BRT; sonda com o corpo real às 12:29-12:42 BRT.
Dados versionados em `desafio_itau/politica/cotas-gemini-v1.json` (1.0.0).

| modelo (ID) | RPM | RPD | uso RPD no painel | sonda | apto |
|---|---|---|---|---|---|
| gemini-3.5-flash-lite | 15 | 500 | 486 | 429 PerDay 12:29 | sim |
| gemini-3.1-flash-lite | 15 | 500 | 1 | 200, 2594 ms | sim |
| gemini-3.6-flash | 5 | 20 | 0 | 200, 1375 ms | sim |
| gemini-3.5-flash | 5 | 20 | 19 | 429 PerDay; antes parado 15 s | sim |
| gemini-3-flash-preview | 5 | 20 | 0 | 200 mas 14937 ms | não |
| gemini-3.7-flash | 5 | 20 | 0 | 503 após 26 s | não |
| gemini-flash-latest (serve 3.8-flash) | 5 | 20 | 26 | 429 PerDay | não |
| gemini-2.5-flash-lite / 2.5-flash | 10 / 5 | 20 | 0 | 404 no generateContent | não |
| gemma-4-26b-a4b-it / 31b-it | 30 | 14400 | 0 | 400 com o corpo real | não |

**Router** (ordem vem do ficheiro; `CONVERSAS['ROTEADOR']` = True por omissão):
Lógica completa, consumo por modelo e procedimento para alterar: [`rotacao-modelos-gemini.md`](rotacao-modelos-gemini.md).


- `input_guard` / `output_guard`: gemini-3.1-flash-lite -> gemini-3.6-flash -> gemini-3.5-flash-lite -> gemini-3.5-flash.
- `generate`: gemini-3.5-flash-lite -> gemini-3.1-flash-lite -> gemini-3.6-flash -> gemini-3.5-flash.
- Por erro: 429/503/404 -> próximo da ordem disponível; 504 -> o de menor `latencia_ref_ms`; 400 -> não troca.
  No máximo 1 nova chamada por etapa (política inalterada).
- Resfriamento por modelo: cota diária 900 s; cota por minuto = `retryDelay` do Google (60 s sem ele); timeout 60 s; 5xx
  30 s; 404 3600 s. O teto de RPM do painel menos 1 é contado neste processo (janela 60 s). Todos bloqueados -> nenhuma
  chamada e erro com o tipo do bloqueio (cota -> 429 `cota_provedor`).
- `GET conversas/status/` expõe `roteador.{ordem_por_etapa, ultimo_modelo_por_etapa, resfriamentos, rpm_no_processo}`.

## 5. Limites conhecidos (não resolvidos aqui)

- **Cota do Gemini (429):** a chave é partilhada e, às 12:29-12:31 BRT, a cota **diária** dos três modelos homologados
  estava esgotada (§4.1). Desde a §4.2 o router desvia para outro modelo com cota (medido: `gemini-3.1-flash-lite` e
  `gemini-3.6-flash` responderam às 13:02). Com todos sem cota, a conversa responde HTTP 429, `tipo=cota_provedor`,
  `acao_cliente=aguardar_e_tentar_novamente`, `tentar_novamente_em_s=30` e `Retry-After: 30` (o cabeçalho era a opção
  (b), aplicada a pedido do coordenador às 12:38). **Decisão do dono (não aplicada):** com cota DIÁRIA esgotada,
  "aguarde 30 s" não é verdade — a cota volta à meia-noite do Pacífico (≈04:00 BRT, NAO_MEDIDO aqui); opções: (a)
  linha própria na política para 429 de cota diária (`aguardar_ou_encaminhar`, espera até o reset), (c) chave
  paga/separada por processo. O `retryDelay` do Google (35-52 s) veio igual para cota diária, então não serve de prazo.
- **404 do provedor** continua a sair com `acao_cliente=reiniciar_sessao` na linha 404 herdada da 1.1.0 (erro do
  modelo, não da sessão); o router já tira esse modelo por 3600 s. Mudar a linha é decisão do dono.
- **Tempo da conversa com router:** medido 24,1 s num turno com 2 trocas (429 no generate + timeout de 10 s no
  output_guard). Pior caso teórico com as duas trocas em timeout: 10+10 + 15+15 + 10+10 = 70 s, cortado pelos 45 s do
  serviço (sai 504 antes dos 50 s do front). NAO_MEDIDO em carga.
- **Timeouts** por etapa desde a §4.1 (guards 10 s, `generate` 15 s). Latência de `generate` com sucesso acima de
  2,3 s: NAO_MEDIDO. Os "estouros" medidos hoje foram do `gemini-3.5-flash` parado (sem resposta) antes de devolver o
  429 diário, não geração lenta; subir o timeout não teria ajudado.
- **Caminho de compromisso com o Gemini real: NÃO verificado** — cota diária do principal esgotada (§4.1) e depois
  orçamento de chamadas da tarefa gasto (§4.2); uma conversa real passou (200, §4.2). Coberto de ponta a
  ponta com gateway falso na forma que o prompt pede (`tests/test_compromisso_caminho_completo.py`). O que prepara o
  caso: pelo menos duas falas do usuário, com objetivo, contexto, ação e valor mensal ditos literalmente (ex.: as 4
  falas do teste), perfil/plano aberto (`GET i-agora/perfil/`) e nenhuma nova mensagem entre o caso e o
  `POST plano/proposta/` (cada mensagem retira o caso não aprovado). Para verificar: depois do reset da cota, correr
  as 4 falas do teste pela :8000 e seguir proposta -> confirmar -> PATCH -> acompanhamento (12 chamadas ao provedor).
- Mês de corte do plano segue o mês atual (como o `agent_backend`), não o `DATA_CORTE` do backend.
- `GCSPlanStore` e `admit_call` do `agent_backend` não foram portados.
