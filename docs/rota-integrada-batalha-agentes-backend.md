# Rota integrada do batalha-agentes: lado backend

Levantado em **2026-09-27 09:02 BRT**, lendo o código desta pasta (`backend-agente-conversacional`, sem git) e o
clone `old/desafio-itau-batalha-de-agentes-time2`. Nenhuma rota foi chamada nesta revisão. Os tempos citados vêm dos
documentos de origem, com a data deles.

**Par no front:** `agente-app-mobile/docs/rota-integrada-batalha-agentes-front.md` **não existia** às 09:02. Os
nomes de botão e de tela vêm de [interacoes-front-back.md](interacoes-front-back.md) §2 (front `2835401`).

**Fontes:** [contrato-api-frontend.md](contrato-api-frontend.md) (§4, §5.1–§5.4),
[interacoes-front-back.md](interacoes-front-back.md), [CHANGELOG-semantica.md](CHANGELOG-semantica.md),
[fluxo-executado-2026-09-27.md](fluxo-executado-2026-09-27.md) §7 e o código citado em cada linha como `arquivo:linha`.

---

## 1. Mapa de montagem

| Prefixo | Inclui | Onde |
| --- | --- | --- |
| `/` | redireciona para `/app/` (302) | `desafio_itau/urls.py:13` |
| `/app/` | `apps.recomendacao.urls` | `desafio_itau/urls.py:16` |
| `/api/v1/context-agent/conversas/` | `apps.conversas.urls` (montado **antes** dos includes largos) | `desafio_itau/urls.py:20` |
| `/api/v1/` | `apps.recomendacao.urls` (de novo) | `desafio_itau/urls.py:23` |
| `/context-agent/` | `apps.context_agent_datadriven.urls` | `desafio_itau/urls.py:26` |
| `/api/v1/context-agent/` | `apps.context_agent_datadriven.urls` (de novo) | `desafio_itau/urls.py:27` |

São **31 padrões de URL**: 1 raiz, 12 em `recomendacao`, 13 em `context_agent_datadriven` e 5 em `conversas`
(incluindo o coringa de 404). Como dois apps são montados duas vezes, isso dá **56 caminhos servidos**.

Convenções comuns:

- Sem autenticação. `CORS_ALLOW_ALL_ORIGINS = True` (`desafio_itau/settings.py:83`).
- As rotas DRF devolvem `{"erro": "..."}`. As de usuário real e perfil juntam `tempo_resposta_ms`
  (`views_usuario_real.py:39`, `views_perfil_usuario.py:40`).
- As rotas de `conversas/` usam envelope próprio, com `Cache-Control: no-store` e `X-Content-Type-Options: nosniff`
  (`apps/conversas/views.py:55-60`, `apps/conversas/views_interacao.py:19-23`).

---

## 2. Catálogo de rotas

### 2.1 Conversa i-agora: `/api/v1/context-agent/conversas/` (só local)

| # | Método e caminho | Headers | Entrada | Saída 2xx | Erros | Código |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | `GET sessao/?sessao_id=` | `X-Sessao-Id` (vale mais que a query); a query só é aceita neste GET | — | 200, envelope `schema_version "1.0"`: `conversation_id: null`, `message_id`, `request_id`, `status`, `reply`, `citations: []`, `mode` (`demo_live`\|`demo`), `usuario {codigo, pessoa, genero, indice}`, `encaminhamento`, `contrato`, `erro_api`. Grava os cookies `conversa_sessao` e `csrftoken` | 404 sem sessão válida (`reply` pede `definir/`) · 405 método · 503 exceção | `apps/conversas/views.py:109-125`, `service.py:60-86` |
| C2 | `POST mensagens/` | `Content-Type: application/json`, `X-CSRFToken` (= cookie `csrftoken`), cookie `conversa_sessao` ou `X-Sessao-Id` (o header vale mais) | `MessageV1` estrito: `schema_version "1.0"`, `conversation_id` (≤ 64 ou null), `client_message_id` (1..80, `[A-Za-z0-9_-]`), `message` (1..2000). Campo extra, incluindo `sessao_id`, dá 400. Corpo ≤ 16 KB | 200, envelope 1.0: `status` `ok`\|`needs_clarification`\|`safe_redirect`, `reply`, `citations`, `dados {estado, selo}` (só na resposta aprovada com titular), `encaminhamento`, `contrato` (sempre), `erro_api` | 400 schema/tamanho · 403 CSRF · 404 sessão ou `conversation_id` desconhecido/expirado · 405 · 409 `client_message_id` repetido com outro corpo · 429 limites · 503 provedor, guard ou timeout de 45 s | `views.py:128-145`, `schemas.py:10-14`, `service.py:88-157` |
| C3 | `POST interacao/` | `X-Sessao-Id` **obrigatório**. Sem cookie e sem CSRF | `{"etapa": str, "escolha"?: str\|null, "mensagem"?: str\|null}`. Outras chaves dão 400. Corpo ≤ 8 KB. `mensagem` com 1..1000 caracteres | 200, `schema_version "1.1"`: ver §2.1.1 | 401 sem header · 404 sessão · 400 schema, etapa ou escolha (com `etapas_validas`) · 405 · 503 (mesmo corpo com `texto: null` e `origem_resposta: "nenhuma"`) | `views_interacao.py:30-63`, `interacao.py:538-665` |
| C4 | `GET avaliacoes/resumo/[?data=AAAA-MM-DD]` | — | — | 200: resumo do ledger `relatorios/avaliacoes/*.jsonl` | 400 data · 405 | `views_interacao.py:66-73` |
| C5 | qualquer outro caminho sob `conversas/` | — | — | — | 404 no envelope 1.0 (`not_found`) | `apps/conversas/urls.py:15`, `views.py:148-150` |

Limites de C2, em memória e por processo:

- 6 pedidos/min por sessão (`service.py:50`, `service.py:130-131`).
- 20 turnos por conversa (`service.py:50`, `service.py:139-140`).
- 5 conversas por sessão e 100 no processo (`service.py:133-134`).
- Um pedido de cada vez **no processo inteiro**: o `lock` é do serviço, não da sessão (`service.py:58`,
  `service.py:97-98`). Dois usuários simultâneos: o segundo recebe 429.

Erro de C3 fora do 503: `{"schema_version": "1.0", "erro": <código>, "mensagem": ...}` (`views_interacao.py:26-27`).

#### 2.1.1 Corpo 200 de `interacao/`

Os campos estão em `interacao.py:627-647`. O contrato §5.3 lista parte deles:

- `schema_version`: `"1.1"`.
- `request_id`, `etapa`, `roteiro_ids`, `escolha`, `turno_livre`, `dominio`.
- `texto`, `origem_resposta`: `modelo` \| `roteiro` \| `dados` \| `fairness` \| `guard_entrada` \| `fora_do_contexto` \|
  `encaminhamento` (`interacao.py:563`).
- `situacao` e `situacao_media`, os dois = sinal do saldo **médio** da janela (`interacao.py:633`).
- `situacao_mes_recente`, `mes_referencia`, `ancora_temporal {janela, registros_ate, base}`.
- `perfil_t3`: segmento ou `NAO_MEDIDO` (`interacao.py:637`).
- `fluxo {id, versao, segmento, situacao, proximo_passo, regras}`, `cenario`.
- `dados`, `selo`, `estado_dados`, `regras_aplicadas`, `proximas_acoes [{id, texto, etapa_seguinte, tipo}]`.
- `avaliacao`: cada tentativa leva `http_status` e `tratamento` (`interacao.py:495-496`).
- `aprovado`, `encaminhamento`, `erro_api` (só quando todas as tentativas falharam no provedor,
  `interacao.py:645-646`), `tempo_total_ms`.

### 2.2 Perfil de usuário: `/api/v1/context-agent/perfil-usuario/` (só local)

| # | Método e caminho | Entrada | Saída 2xx | Erros | Código |
| --- | --- | --- | --- | --- | --- |
| P1 | `POST definir/` | `{"usuario": "<índice 1..N \| UUID>"}` (texto ou inteiro, ≤ 64) | 201 `{sessao_id (uuid4 hex), usuario {codigo, pessoa, genero, indice}, expira_em_segundos: 14400, tempo_resposta_ms}` | 400 referência · 404 usuário fora do CSV · 503 `estado: "NAO_MEDIDO"` sem o CSV | `views_perfil_usuario.py:54-59`, `services/perfil_usuario.py:83-112` |
| P2 | `POST pergunta/` | `{"sessao_id", "pergunta"}` (≤ 2000). Aqui o `sessao_id` **vai no corpo** | 200 `{sessao_id, usuario, pergunta, intencao, resposta, modelo, origem_resposta, guard {estado: "APROVADO", conferido}, tempo_resposta_ms}` | 400 · 404 sessão · 502 `guard {estado: "REPROVADO", faltam}` · 503 nenhum modelo | `views_perfil_usuario.py:62-67`, `services/perfil_usuario.py:172-199` |

### 2.3 Usuário real (BigQuery): `/api/v1/context-agent/` (publicado)

Os erros são comuns às rotas de `views_usuario_real.py:25-39`:

| HTTP | Quando | Corpo extra |
| --- | --- | --- |
| 400 | referência ou `data_corte` inválida; `limite`/`offset` não inteiros | — |
| 404 | usuário inexistente | — |
| 422 | tópico ou categoria fora do catálogo | — |
| 503 | fonte desligada | `estado: "OFF"` |
| 503 | BigQuery falhou | `estado: "NAO_MEDIDO"` |

| # | Método e caminho | Entrada | Saída 200 (resumo) | Código · contrato |
| --- | --- | --- | --- | --- |
| U1 | `GET usuario-real/status/[?validar=1]` | — | `estado`, `projeto`, `tabela`, `data_corte_padrao`, `cache_segundos`, `topicos`, `categorias`, `conexao` (`VALIDADA`\|`FALHOU`\|`NAO_MEDIDO`), `selo` | `views_usuario_real.py:42-47` · §4.1 |
| U2 | `GET usuario-real/?limite=&offset=` | `limite` 1..1000 (padrão 20), `offset` ≥ 0 | `{total, limite, offset, usuarios[], selo}` | `views_usuario_real.py:50-63` · §4.2 |
| U3 | `GET usuario-real/<ref>/[?data_corte=]` | ref = índice ou UUID | `{usuario, data_corte, janela, resumo, visoes, sql_sha256, selo}` | `views_usuario_real.py:66-70` · §4.3 |
| U4 | `GET usuario-real/<ref>/visao/<topico>/[?categoria=&data_corte=]` | tópico ∈ `perfil_t3`, `categoria`, `renda`, `dividas`, `recorrencias`, `discricionario` | `{usuario, topico, parametros, linha, sql_sha256, selo}` | `views_usuario_real.py:73-78` · §4.4 |
| U5 | `GET usuario-real/<ref>/saldo-mes/[?data_corte=]` | — | `{periodo, entradas, saidas, saldo, lancamentos, negativado, media_mensal, negativado_na_media, selo}` | `views_usuario_real.py:81-85` · §4.6 |
| U6 | `POST usuario-real/<ref>/pergunta/` | `{"pergunta", "data_corte"?}`. Pergunta vazia: 400 | `{pergunta, categoria, topico, linha, selo}`. Não chama LLM | `views_usuario_real.py:107-116` · §4.5 |
| U7 | `GET\|POST i-agora/plano/proposta/` | `{"ref", "data_corte"?}` ou `?ref=`. Sem ref: 400 | `{estado, compromissos[], totais, apresentacao, selos}` | `views_usuario_real.py:88-104` · §4.7 |
| U8 | `GET controle-conversa/[?estagio=]` | estágio desconhecido: 400 | `{versao_roteiro, falas[{id, estagio, texto, variaveis, versao_roteiro}], total_falas, ...}` | `views_controle_conversa.py:55-69` · §4.8 |

### 2.4 Agente legado (Gemini) e painel: `/api/v1/context-agent/` (publicado)

| # | Método e caminho | Entrada | Saída | Erros | Código |
| --- | --- | --- | --- | --- | --- |
| G1 | `GET status-harness/[?validar=1]` | — | 200 com `secret_gsconsole.status` e `validacao` | — | `views.py:29-64` · CHANGELOG #5 |
| G2 | `POST primeira-chamada/` | **só** `{"texto_inicial"}` (≤ 2000) | 200 `{sucesso, modelo, resposta, tempo_resposta_ms}` | 400 · 503 `{erro}` | `views.py:191-208` · CHANGELOG #9 |
| G3 | `POST enviar-mensagem/` | `{"mensagem", "cliente_id"?, "cliente_nome"?, "contexto"?}` | 200, `origem_resposta: "modelo"` | 400 · 503 `origem_resposta: "contingencia"` | `views.py:66-120`, `views.py:127` · CHANGELOG #2, #3, #8 |
| G4 | `GET ` (raiz de `context-agent/`) | — | painel HTML | — | `views.py:182-188` |

G3 ainda usa o **cliente demo** do SQLite, não o usuário real (contrato §5).

### 2.5 Cliente demo, telas e chave (SQLite): `/api/v1/` e `/app/` (publicado)

| # | Método e caminho | Saída 200 | Erros | Código |
| --- | --- | --- | --- | --- |
| D1 | `GET\|POST chave-interacao-tela-iai/` | `{codigo, nome, estado, chave_ativa, ...}`. POST `{}` alterna; `{"chave_ativa": bool}` fixa | 400 tipo · 500 gravação | `recomendacao/views.py:23-82` |
| D2 | `GET cliente/random/[?genero=F\|M]` | cliente demo | — | `recomendacao/views.py:110-121` |
| D3 | `GET cliente/<id>/` | cliente demo | 404 fora de 1..1000 · 400 | `recomendacao/views.py:98-108`, `:86-87` |
| D4 | `GET grupos-fixos/` | estatísticas F/M | — | `recomendacao/views.py:123-143` |
| D5 | `GET chat/variavel-1/<id>/` | conversa pré-preenchida | 404 · 400 | `recomendacao/views.py:145-173` |
| D6 | `GET\|POST comunicacao/e-agora/<id>/` | payload do Template 3 | 404 · 400 | `recomendacao/views.py:175-192` |
| D7 | `GET contexto-score/<id>/` | índice de corte e diretriz | 404 · 400 | `recomendacao/views.py:195-206` |
| D8 | `GET planilha-fixa/` | `{descricao, total_itens, itens}` | — | `recomendacao/views.py:208-215` |
| D9–D11 | `GET ` (dashboard), `GET chat/<id>/`, `GET comunicacao/<id>/` (HTML) | página | 404 HTML | `recomendacao/views.py:221-229`, `:248`, `:267` |

---

## 3. Headers, cookies e sessão

| Item | Valor real | Onde |
| --- | --- | --- |
| `X-Sessao-Id` | o `sessao_id` de P1. Obrigatório em C3; opcional em C1/C2, onde vale mais que query e cookie. Até 64 caracteres | `views.py:67-81`, `views_interacao.py:34-40` |
| Sessão do perfil | memória do processo, **4 h** (`SESSAO_SEGUNDOS = 4 * 60 * 60`). Reiniciar o Django apaga todas | `services/perfil_usuario.py:27`, `:103-123` |
| Cookie `conversa_sessao` | assinado (`signing`, salt = nome do cookie), HttpOnly, SameSite=Lax, `secure` só em HTTPS, `max_age` = **14.400 s (4 h)** | `views.py:30`, `views.py:72`, `views.py:123-124` |
| Cookie `csrftoken` | `ensure_csrf_cookie` em C1. A idade não é definida em `settings.py`, então vale o padrão do Django: `60*60*24*7*52` s (**52 semanas**) | `views.py:111`; `frontend-agent-conversacional/.venv/.../django/conf/global_settings.py:571` |
| `X-CSRFToken` | exigido em C2. O CSRF é aplicado **na view**, porque não há `CsrfViewMiddleware` global | `views.py:97-107`, `views.py:133-135`; `settings.py:33-38` |
| `CSRF_TRUSTED_ORIGINS` | só `http://127.0.0.1:3000` e `http://localhost:3000` | `settings.py:120` |
| Conversa (`conversation_id`) | memória do `ConversationService`, `ttl=1800` s (**30 min**) desde a criação | `service.py:50`, `service.py:104-109` |

---

## 4. Fluxo por etapa do front (`POST conversas/interacao/`)

A tabela vem de `ETAPAS` (`interacao.py:48-108`). "Consulta BigQuery" vem de `coletar` (`interacao.py:147-199`):
toda etapa lê `perfil` e `mensal`. `proposta` só é lida onde a coluna diz sim. `subcategorias` só é lida em turno livre.

| Etapa | Botões → etapa seguinte | Chama Gemini | Números no texto | Proposta | Botão no front (interacoes §2) | Código |
| --- | --- | --- | --- | --- | --- | --- |
| `home.visao_conta` | `home.botao_conferir` "Conferir" → `bot.intro` | **não** (`gemini: False`). Texto montado pelo servidor, `origem_resposta: "dados"` | **sim**: saldo, entradas e saídas **médios** da janela | não | "Conferir" (2.2) | `interacao.py:49-52`, `:580-585` |
| `bot.intro` | `intro.carrossel.1` (tipo `automatica`) → `intro.carrossel.1`; `intro.gatilho_agora` "i.agora" → `bot.convite_50_30_20` | sim | não (`numeros: False`) | não | Intro (2.3) | `interacao.py:53-58` |
| `intro.carrossel.1` | `intro.gatilho_agora` → `bot.convite_50_30_20` | sim | sim (média mensal da janela) | não | — | `interacao.py:59-65` |
| `bot.convite_50_30_20` | `user.topo_desafio` "Topo o desafio" → `bot.confirm` | sim | sim (percentuais 50-30-20) | não | `button-open-iagora` (2.4) | `interacao.py:66-72` |
| `bot.confirm` | `user.assumir` → `bot.card`; `user.ajustar` → `user.ajustar` | sim | sim (compromissos e valor liberado) | **sim** | `button-start-plan` (2.5) | `interacao.py:73-82` |
| `user.ajustar` | `user.assumir` → `bot.card` | sim | não | não | `button-adjust-values` (2.7) | `interacao.py:83-88` |
| `bot.card` | `card.salvar` / `card.baixar` → `bot.finish`; `card.outra_frase` → `bot.card`; `card.voltar` → `home.visao_conta` | sim | não | **sim** | `button-assume-commitments` (2.6); `button-save-image` / `button-download-image` / `button-change-phrase` (2.8) | `interacao.py:89-95` |
| `bot.finish` | `finish.voltar` → `home.visao_conta` | sim | não | não | — | `interacao.py:96-100` |
| `livre.respostas` | nenhum | sim | só os de `DADOS` | não | `button-send-message` (2.9) | `interacao.py:101-107` |

Desvios do caminho normal, na ordem de `interagir` (`interacao.py:553-604`):

1. `mensagem` em qualquer etapa vira turno livre com a configuração de `livre.respostas` (`interacao.py:547`, `:552`).
2. Extremo detectado por regra: texto fixo, sem modelo e sem consulta (`interacao.py:559-563`).
3. Fora do domínio financeiro: texto fixo `cn.FORA_DO_CONTEXTO`, sem modelo e sem consulta (`interacao.py:564-568`).
4. `CONVERSAS_MODO=demo`: sem Gemini; cai no roteiro (`interacao.py:588-589`, `:603-604`).
5. Turno livre com guard de entrada ligado: +1 chamada ao último modelo da lista (`interacao.py:590-594`).
6. Nenhum modelo aprovado: texto do roteiro (`origem_resposta: "roteiro"`). Se nem ele passa nos guards: 503
   (`interacao.py:603-604`, `:662-664`).
7. Cenário `consolidacao_divida`: acrescenta `handoff.consolidacao` em `proximas_acoes`. A rota de atendimento é
   **NAO_IMPLEMENTADO** (`interacao.py:625-626`; contrato §5.3).

---

## 5. Contrato novo da §5.4 (publicado no doc às 09:00, conferido no código às 09:02)

O texto está em [contrato-api-frontend.md §5.4](contrato-api-frontend.md#54-campos-novos-no-envelope-aditivos-2026-09-27-contrato-e-erro_api).
Ele não é copiado aqui. A tabela abaixo confere cada afirmação com o código.

| Afirmação da §5.4 | Código | Bate? |
| --- | --- | --- |
| `mensagens/` devolve sempre `contrato` | `service.py:83-84`: o default `estado.contrato(...)` entra quando não vem contrato | sim |
| `contrato` tem `estado`, `acoes_permitidas`, `evidence_ids`, `periodo`, `racional`, `regras` | `schemas.py:53-64` e `estado.py:107-117`: o campo chama-se **`regras_aplicadas`**. Há também `schema_version`, `informacoes_faltantes` e `limitacoes_materiais` | **não** (D5) |
| Os 9 valores de `estado` | `schemas.py:42-43`, `estado.py:41-56` | sim |
| `erro_api` null quando não houve erro | `erros_api.py:86-90`: sai null para todo código fora de 400/404/429/503/504, ou seja, também em 401, 403, 405 e 409 | **parcial** (D6) |
| Tabela 400/404/429/503/504 com `acao_cliente` e `encaminhar_humano` | `erros_api-v1.json:13-67`: 503 e 504 com `encaminhar_humano: true`; espera 0/0/30/10/15 s | sim |
| No máximo 1 nova chamada, ao modelo alternativo, nunca o mesmo modelo | `gateway.py:81-84`, `:139-151`; `erros_api-v1.json:8` (`novas_chamadas_max: 1`) | sim |
| 503: espera ≤ 2 s antes da nova chamada | `erros_api.py:78-83`; `erros_api-v1.json:9` | sim |
| Falha do provedor: HTTP 503 e `erro_api.origem = "provedor"` | `service.py:150-154`. Se o status do provedor for desconhecido, `erro_api` volta null e `service.py:85` o troca por 503 com `origem: "api"` | **parcial** (D7) |
| `interacao/`: tentativas ganham `http_status` e `tratamento` | `interacao.py:495-496`, `:620` | sim |
| `interacao/`: `erro_api` quando todas falham; sem nova chamada interna | `interacao.py:645-646`; `interacao.py:369` (`novas_chamadas = False`) | sim |

**Observação:** o alternativo do modelo principal `gemini-3.5-flash-lite` é `gemini-flash-latest`
(`gateway.py:83`, `modelos_llm.py:12-18`). Segundo o contrato §5.3, esse modelo deu 429 durante todo o dia 2026-09-27.

**Proposta da sessão f7:** tratar `conversas/interacao/` como "rota de fluxo" (decisão por `origem_resposta`) e usar
`contrato.estado` como o schema fixo que falta a ela. **Hoje `interacao/` não devolve `contrato`**: o corpo não tem
esse campo (`interacao.py:627-647`). A proposta está **pendente de decisão do dono**, porque é uma mudança de
produto (interacoes-front-back §7).

---

## 6. Dependências

| Dependência | Como liga | Valor real | Onde |
| --- | --- | --- | --- |
| BigQuery | ADC (`gcloud auth application-default login`) | projeto `batalha-time-02-lxof`, tabela `batalha-time-02-lxof.hackathon_dados.extrato_sintetico`, corte `2025-12-22` | `settings.py:104-110` |
| Cache do usuário real | memória do processo | 900 s (`USUARIO_REAL_CACHE_SEGUNDOS`) | `settings.py:109`, `services/usuario_real.py:76` |
| Gemini | chave em `obter_api_key()`: env `API_KEY_SECRECT` > arquivo (`SECRETS_FILE` > `../.secrets` > `../frontend-agent-conversacional/.secrets`) > envs legadas | modelos `gemini-3.5-flash-lite` (principal e contingência) e `gemini-flash-latest` | `segredos.py:29-35`, `:62-77`; `modelos_llm.py:12-18` |
| Orçamento Gemini | por processo | 300 chamadas (máx. 3000); cada mensagem de C2 gasta 3 | `settings.py:115-118` |
| SQLite | `init_database.py` | `db.sqlite3` na raiz do backend | `settings.py:63-68` |
| CSV da verdade | `scripts/baixar_usuarios_verdade.py` | `data/usuarios_verdade.csv` (+ `.selo.json`) | `services/perfil_usuario.py:26`, `:69-80` |
| Política | JSON versionado | `desafio_itau/politica/*.json` (operacional, erros_api, léxico, comunicação) | `estado.py:12-13`, `erros_api.py:18` |
| Ledger de avaliação | arquivo | `relatorios/avaliacoes/<data>.jsonl` | `interacao.py:649-661` |

### Variáveis de ambiente

| Variável | Padrão | Efeito | Onde |
| --- | --- | --- | --- |
| `USUARIO_REAL_ATIVO` | `1` | `0`/`false`/`off`/`nao` desliga → 503 `OFF` | `settings.py:105` |
| `USUARIO_REAL_PROJETO` | `batalha-time-02-lxof` | projeto do cliente BigQuery | `settings.py:106` |
| `USUARIO_REAL_CACHE_SEGUNDOS` | `900` | validade do cache | `settings.py:109` |
| `CONVERSAS_MODO` | `demo_live` | `demo` = texto fixo, sem IA | `settings.py:116` |
| `CONVERSAS_MAX_CHAMADAS` | `300` | orçamento Gemini por processo, limitado a 0..3000 | `settings.py:117` |
| `INTERACAO_GUARD_ENTRADA_MODELO` | `1` | `0` desliga o guard de entrada por modelo em C3 | `views_interacao.py:54` |
| `API_KEY_SECRECT` | — | chave Gemini (maior precedência) | `segredos.py:19`, `:64-66` |
| `SECRETS_FILE` | — | caminho do `.secrets` | `segredos.py:30-31` |
| `GEMINI_API_KEY`, `GSCONSOLE_SECRET`, `GOOGLE_API_KEY` | — | legado, só se nada acima existir | `segredos.py:20`, `:72-75` |

---

## 7. PUBLICADO vs SÓ LOCAL

**Publicado** = clone `old/desafio-itau-batalha-de-agentes-time2`, `main` alinhado com `origin/main` no ref local
(`7f6a7c0`, 2026-09-27 06:47:34 −03:00). **O `git fetch` não foi rodado nesta revisão**: um commit mais novo no
GitHub é NAO_MEDIDO.

| Peça | Publicado (git) | Só local (esta pasta) | Prova |
| --- | --- | --- | --- |
| Usuário real U1–U6, proposta U7 | sim | sim | clone `apps/context_agent_datadriven/urls.py:28-33`, `:25` |
| `controle-conversa/` U8 | sim, roteiro `2026-09-27.3` | sim, roteiro `2026-09-27.4` | `roteiro.json:2` nos dois |
| Agente legado G1–G4 e cliente demo D1–D11 | sim | sim | clone `urls.py` |
| `perfil-usuario/` P1–P2 | **não** | sim | ausente no clone; `services/perfil_usuario.py` não está em `git ls-files` |
| `conversas/` C1–C5 (`apps/conversas/`) | **não** | sim | clone `desafio_itau/urls.py` não monta; `apps/conversas` não está em `git ls-files` |
| `desafio_itau/politica/` (contrato §5.4) | **não** | sim | ausente em `git ls-files desafio_itau` |
| `CONVERSAS` e `CSRF_TRUSTED_ORIGINS` em settings | **não** | sim | clone `settings.py` só tem `USUARIO_REAL` (linha 103) |
| `data/usuarios_verdade.csv` | **não** | sim | `git ls-files data` vazio |
| Contrato §5.1–§5.4 | **não** (o clone não tem subseções 5.x) | sim | clone `docs/contrato-api-frontend.md`, 374 linhas |
| `agent_backend/conversation/` (origem do porte) | versionado (41 arquivos), mas **não montado** no `desafio_itau/urls.py` do clone | — | clone `agent_backend/harness/urls.py:4` |

Isso confirma o que diz [fluxo-executado-2026-09-27.md](fluxo-executado-2026-09-27.md) §7: as rotas de perfil-usuario e
de conversas estão fora do git.

---

## 8. Divergências conhecidas

| # | Divergência | Evidência |
| --- | --- | --- |
| D1 | **Dez/2025 publicado vs média jan–nov na conversa.** U5 `saldo-mes` (publicado) devolve o saldo de 01/12 a 22/12. A conversa (só local) decide `situacao` e mostra em `home.visao_conta` o saldo **médio** de jan–nov/2025. O `mes_referencia` da conversa é **novembro**. O cartão do front mostra dezembro sintético. São três "saldos" para a mesma tela | `views_usuario_real.py:81-85`; `interacao.py:580-585`, `:633-635`; `interacao_dados.py:156-157`, `:229-238`; interacoes-front-back §1 |
| D2 | **`perfil_t3` sai na API sem guard que impeça o rótulo no texto.** O segmento vai no corpo e no contexto dado ao modelo (C3) e aos fatos (C2). Os termos proibidos por perfil não incluem "Vulnerável", "Esbanjador" nem "Livre". O léxico só bloqueia a forma "você é esbanjador". Uma frase como "seu perfil é Vulnerável" passa. Não se mediu se o modelo já escreveu isso | `interacao.py:637`, `:303`; `context.py:23`; `pastas_raiz/estudos/i_agora/t3.py:119`, `:127`, `:135`; `politica/lexico-v1.json:38` |
| D3 | **Cookie "30 dias" vs conversa 30 min.** Neste backend, o cookie `conversa_sessao` e a sessão do perfil valem 4 h, e a conversa vale 30 min. Os **30 dias** são do outro backend (`agente-app-mobile`, cookie `i_agora_demo_session`, `IAGORA_SESSION_AGE`), não deste. Efeito aqui: depois de 30 min, o `conversation_id` dá 404 com a sessão ainda viva. O front deve reenviar `conversation_id: null` | `perfil_usuario.py:27`; `views.py:72`, `:123-124`; `service.py:50`, `:104-109`, `:121-122`; `agente-app-mobile/deploy/settings.py:16`; `agente-app-mobile/agent_backend/conversation/http.py:59`, `:92` |
| D4 | O `csrftoken` vive 52 semanas; a sessão, 4 h | `global_settings.py:571` (Django), `settings.py` sem `CSRF_COOKIE_AGE` |
| D5 | §5.4 diz `contrato.regras`; o código emite `regras_aplicadas` e mais 3 campos que a §5.4 não cita | `schemas.py:56-64`; `estado.py:105-112` |
| D6 | §5.4: "`erro_api` null quando não houve erro". Também sai null em 401, 403 (CSRF), 405 e 409 | `erros_api.py:51`, `:86-90` |
| D7 | Falha do provedor com status fora da tabela (ex.: exceção sem `code`) sai com `erro_api.origem = "api"` e código 503, não `"provedor"` | `service.py:150-154`, `:85` |
| D8 | O contrato §4.8 diz roteiro `2026-09-27.2` com 45 falas. O local está em `.4` e o publicado em `.3` | `conversa/roteiro.json:2` (local e clone) |
| D9 | O corpo 200 de `interacao/` tem campos que o contrato §5.3 não lista (`schema_version "1.1"`, `request_id`, `roteiro_ids`, `dominio`, `situacao_mes_recente`, `ancora_temporal`, `encaminhamento`, `erro_api`). Os erros 4xx da mesma rota saem com `schema_version "1.0"` | `interacao.py:627-647`; `views_interacao.py:26-27` |
| D10 | interacoes-front-back §3.2 ainda diz que `interacao/` está "em construção"; o código e o contrato §5.3 a descrevem pronta | interacoes-front-back §3.2; `interacao.py:538-665` |
| D11 | O `lock` de C2 é global: um pedido de um usuário devolve 429 a outro usuário simultâneo | `service.py:58`, `:97-98` |
| D12 | `CSRF_TRUSTED_ORIGINS` só aceita a porta 3000. O contrato §1 manda usar o Vite na 3001 quando a 8000 está ocupada. Um POST `mensagens/` vindo de `:3001` pode dar 403. **NAO_MEDIDO**: depende do header `Origin` que o proxy repassa | `settings.py:120`; contrato §1 |
| D13 | `USUARIO_REAL_PROJETO` muda o projeto, mas `TABELA` é fixa em `batalha-time-02-lxof` | `settings.py:106-107` |

---

## 9. NAO_MEDIDO

- Se o GitHub tem commit mais novo que `7f6a7c0`: não foi rodado `git fetch`.
- Nenhuma rota foi chamada nesta revisão: status, latência e corpo real ficaram fora. Os tempos deste documento
  são os dos documentos de origem.
- Se o modelo já escreveu o rótulo T3 no texto (D2): não há teste nem ledger consultado para isso.
- Efeito real do CSRF com o proxy na 3001 (D12).
- Número exato de falas do roteiro `.4`: `roteiro.json` tem 211 ocorrências de `"id"`, mas nem todas são falas.
- O corpo de C4 (`avaliacoes/resumo/`) campo a campo: `interacao_avaliacao.resumo` não foi lido.
- A validação interna de G3 (`views.py:127-180`) além do que o CHANGELOG #3 descreve.
- O documento par do front: não existia às 09:02.
