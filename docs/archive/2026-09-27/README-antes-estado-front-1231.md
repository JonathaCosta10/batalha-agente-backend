# backend-agente-conversacional — i.agora (Django)

Backend **Django 5 + DRF** do **i.agora**, o assistente de planejamento financeiro da Batalha de Agentes Itaú
(Time 2). O fluxo tem quatro passos:

1. O front identifica a pessoa cliente, um dos 1.000 `id_usuario` do extrato sintético no BigQuery.
2. O backend mede os dados dessa pessoa no BigQuery: perfil T3, médias mensais, proposta de cortes para janeiro.
3. O Gemini redige o texto.
4. Guards determinísticos aprovam ou reprovam essa redação. Se reprovarem, o backend serve a fala fixa do roteiro.

A norma de referência é a BCB RC 8/2023.

> Documento consolidado em 2026-09-27. As versões anteriores estão em `docs/archive/2026-09-27/`
> (ver `docs/archive/INDICE.md`).
> **Esta pasta não é um repositório git.** O código também vive, portado, em `agente-app-mobile/agent_backend`
> (ver [Etapa 0](#etapa-0--onde-este-projeto-está-no-ecossistema)).

## Sumário

0. [Onde este projeto está no ecossistema](#etapa-0--onde-este-projeto-está-no-ecossistema)
1. [Rodar localmente](#etapa-1--rodar-localmente)
2. [Configuração (variáveis de ambiente)](#etapa-2--configuração)
3. [Arquitetura por módulo](#etapa-3--arquitetura-por-módulo)
4. [Pipeline de uma interação](#etapa-4--pipeline-de-uma-interação)
5. [Contrato HTTP](#etapa-5--contrato-http)
6. [Dados](#etapa-6--dados)
7. [Encaixe com o front](#etapa-7--encaixe-com-o-front-verificação-sistêmica)
8. [Verificação (testes)](#etapa-8--verificação)
9. [Limitações conhecidas](#etapa-9--limitações-conhecidas)
10. [Mapa da documentação](#etapa-10--mapa-da-documentação)

---

## Etapa 0 — Onde este projeto está no ecossistema

```
                         ┌──────────────────────────────────────────────┐
  Navegador (mobile)     │  frontend-agent-conversacional  (React/Vite) │
  pessoa cliente  ─────► │  main: 2 chamadas HTTP (proposta, saldo-mes)  │
                         └───────────────┬──────────────────────────────┘
                                         │ /api/v1/*  (proxy Vite no dev = mesma origem)
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ backend-agente-conversacional  (ESTE — Django, porta 8000)                           │
│  /api/v1/context-agent/…          identidade, usuário real, proposta, roteiro          │
│  /api/v1/context-agent/conversas/ interacao/ (etapas + Gemini + guards), mensagens/  │
│  /api/v1/…  e  /app/…             demo legada de recomendação (1.000 clientes fictícios)│
└──────┬──────────────────────────────┬───────────────────────────────┬────────────────┘
       │ ADC                          │ x-goog-api-key (REST)         │ SQLite
       ▼                              ▼                               ▼
 BigQuery batalha-time-02-lxof   Gemini (gemini-3.5-flash-lite,   db.sqlite3 (sessões,
 .hackathon_dados.extrato_       gemini-flash-latest)             clientes demo, cache)
 sintetico  (dados medidos)
```

| Peça | Papel | Onde |
| :--- | :--- | :--- |
| **Este backend** | Mede, redige com guard e serve o roteiro. Fonte de verdade dos números. | aqui |
| **Front `main`** | Telas i.agora. Consome só `i-agora/plano/proposta/` e `usuario-real/<ref>/saldo-mes/`. | `../frontend-agent-conversacional` |
| **Front publicado** | Branch `feat/i-agora-gcp-integrado`, no Cloud Run. Usa rotas `i-agora/perfil/`, `i-agora/plano/` (GET/PATCH/DELETE), `plano/confirmar/`, `sessao/abertura/` e `conversas/mensagens/`. Desde 2026-09-27 as rotas `i-agora/*` existem **neste backend** (`apps/i_agora`, porte de `Frontend/agent_backend/planning`): o front fala só com este Django. | `../frontend-publicado-wt` |
| **agente-app-mobile** | Entrega consolidada (front + `agent_backend`). `apps/conversas/` daqui foi portado de lá. | `../agente-app-mobile` |

---

## Etapa 1 — Rodar localmente

Não existe `.venv` nesta pasta. O ambiente que funciona hoje (Django 5.0.14, DRF 3.17.2) é o do front irmão.
A medição foi `manage.py check` sem problemas, em 2026-09-27.

```powershell
cd backend-agente-conversacional
$PY = '..\frontend-agent-conversacional\.venv\Scripts\python.exe'
# (ou crie o seu: python -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements.txt)

& $PY manage.py check
& $PY init_database.py                    # migrate + 1.000 clientes demo, 5 produtos, chave ON (idempotente)
& $PY manage.py runserver 127.0.0.1:8000  # a raiz / redireciona para /app/
```

Pré-requisitos para os dados reais e o LLM:

| Recurso | Como | Sem ele |
| :--- | :--- | :--- |
| BigQuery | `gcloud auth application-default login` (ADC) | rotas `usuario-real/*` e proposta respondem **503 `NAO_MEDIDO`** (nunca zero) |
| Gemini | `API_KEY_SECRECT` (ambiente) ou `.secrets` (ver Etapa 2) | a conversa serve a fala do roteiro; `primeira-chamada/` responde 503 |
| CSV de identidades | `data/usuarios_verdade.csv` (gerado por `scripts/baixar_usuarios_verdade.py`) | `perfil-usuario/definir/` responde 503 |

Com o front: rode o Django na porta 8000 e depois rode `npm run dev` no front, que abre na porta 3000 e faz proxy
de `/api/v1` para cá. Se usar outra porta, defina `$env:DJANGO_URL` antes de rodar o front.

**Docker / Cloud Run:** o `Dockerfile` (Python 3.12-slim, usuário 10001, `PORT=8080`, `SQLITE_PATH=/tmp/db.sqlite3`)
roda `init_database.py && gunicorn desafio_itau.wsgi:application --workers 1 --threads 4 --timeout 120`.
O cabeçalho do próprio Dockerfile diz que a imagem **ainda não foi construída nem publicada** a partir desta pasta.

---

## Etapa 2 — Configuração

Todas as variáveis são opcionais no local; os valores padrão estão em `desafio_itau/settings.py`.

| Grupo | Variáveis | Efeito |
| :--- | :--- | :--- |
| Django | `DJANGO_DEBUG`/`DEBUG`, `DJANGO_SECRET_KEY`/`SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`/`ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`/`CSRF_TRUSTED_ORIGINS`, `SQLITE_PATH` | Com `DEBUG=0`, a `SECRET_KEY` passa a ser obrigatória. |
| CORS | `FRONT_ORIGENS`, `CORS_ALLOW_ALL` | Padrão: `localhost`/`127.0.0.1` nas portas 3000 e 3001 (decisão D-5). `CORS_ALLOW_ALL=1` reabre para qualquer origem. |
| Usuário real | `USUARIO_REAL_ATIVO`, `USUARIO_REAL_PROJETO`, `USUARIO_REAL_CACHE_SEGUNDOS` | `USUARIO_REAL_ATIVO=0` desliga o BigQuery (respostas 503 `OFF`). |
| Conversa | `CONVERSAS_MODO` (`demo_live`\|`demo`), `CONVERSAS_MAX_CHAMADAS`, `INTERACAO_GUARD_ENTRADA_MODELO` | Modo de conversa, orçamento de chamadas por processo e modelo do guard de entrada. |
| Chave Gemini | `API_KEY_SECRECT` → `SECRETS_FILE` → `../.secrets` ou `../frontend-agent-conversacional/.secrets` → legado `GEMINI_API_KEY`, `GSCONSOLE_SECRET`, `GOOGLE_API_KEY` | Resolvida em `desafio_itau/segredos.py`, nessa ordem. `API_KEY_SECRECT` é a grafia usada no código. |

Os modelos estão definidos em `desafio_itau/modelos_llm.py`: `MODELO_PRIMEIRA_CHAMADA = "gemini-3.5-flash-lite"` e
`MODELOS_GOOGLE = ["gemini-3.5-flash-lite", "gemini-flash-latest"]`. Os clientes Anthropic e OpenAI em
`agentes/LLM_Models/` são **stubs**: devolvem texto fixo e não chamam nenhum provedor.

---

## Etapa 3 — Arquitetura por módulo

```
desafio_itau/                projeto: settings, urls, saude.py (/healthz), segredos.py, modelos_llm.py,
                             politica/ (JSONs versionados: operacional, lexico, erros_api, comunicacao, produtos, comportamento)
apps/
  context_agent_datadriven/  identidade, usuário real (BigQuery), proposta de cortes, roteiro de falas
  conversas/                 conversa i.agora: interacao/ por etapa + mensagens/ livre  (montado só por URL, sem models)
  recomendacao/              demo legada: 1.000 clientes fictícios, score, templates HTML
templates/                   HTML da demo de recomendação
skills/                      skill extracao-comportamental-iai (ainda não chamada pelo front nem pelo Django)
scripts/                     avaliação de LLM, download do CSV, revisão Gemini, conferência RC 8
notebooks/                   estudo i.agora (cópia do Colab) e regras da batalha
datasets/                    evidências offline (baterias, corpus de intenção) — o runtime não lê
data/                        usuarios_verdade.csv + selo (lido em runtime)
relatorios/                  ledgers gerados (avaliacoes/<data>.jsonl, skills, revisão)
```

### 3.1 `apps/context_agent_datadriven` — dados medidos e identidade

| Serviço | Responsabilidade |
| :--- | :--- |
| `services/perfil_usuario.py` | Resolve índice `1..1000` ou UUID pelo CSV. Cria a `SessaoPerfilUsuario` (TTL de 4 h aplicado na leitura). Responde "quem sou eu" com o guard `conferir`. |
| `services/usuario_real.py` | Lê o BigQuery com cache e **selo** (fonte, jobs, bytes, `medido_em`): perfil, visões por tópico, `saldo_mes`. |
| `services/plano_proposta.py` | Aplica a regra `corte_seguro_ate_surplus_15`: corta subcategorias de Nível 1 e 2 até a sobra chegar a 15 % da renda. O resultado tem um de três estados: `OK`, `LIVRE_SEM_CORTE` ou `CORTE_INSUFICIENTE`. |
| `pastas_raiz/estudos/i_agora/` | SQL das visões, `t3.py` (segmentação Vulnerável/Esbanjador/Livre, `PERFIS_DE_RESPOSTA`), `guard.py`, `visoes.py`. |
| `conversa/roteiro.json` | Falas fixas das etapas (versão `2026-09-27.4`), servidas em `controle-conversa/`. |
| Legado | `rotas/`, `agentes/agente.py`, os models `ConversaAgenteSessao` e `MensagemAgenteRegistro` (da rota `enviar-mensagem/`, hoje **410**). |

O modelo vivo é `SessaoPerfilUsuario`, com os campos `sessao_id` (pk), `usuario_json` e `criada_em`.

### 3.2 `apps/conversas` — a conversa

| Arquivo | Responsabilidade |
| :--- | :--- |
| `interacao.py` | Rota principal por **etapa**: valida etapa e escolha, coleta os dados, redige, avalia e usa o roteiro como fallback. |
| `interacao_dados.py` | SQL mensal e SQL por subcategoria no BigQuery. |
| `interacao_avaliacao.py` | Guards determinísticos: números, situação, nome, política, 50-30-20, ortografia, fluxo, cenário, alucinação, período e tom. Também grava o ledger JSONL. |
| `interacao_cenarios.py` | Classificador de domínio e cenários (pergunta fora do domínio → resposta fixa, sem BigQuery nem Gemini). |
| `extremos.py`, `fairness.py` | Detecta por regra flerte, ameaça, autolesão, abuso e extremo financeiro, e encaminha para humano ou segurança. |
| `gateway.py` | `GeminiGateway`: input_guard → generate → output_guard, via REST `urllib`, com timeout de 15 s. |
| `service.py`, `persistencia.py` | `ConversationService` da rota `mensagens/` e a tabela de cache `conversas_sessao_cache`. |
| `prompts/*.liquid`, `knowledge/*.json` | Prompts renderizados e a base normativa (RC 8/2023, RC 20/2026, institucional). |

### 3.3 `apps/recomendacao` — demo legada

É independente das outras apps. Contém os models `ClienteRegistro`, `PlanilhaProdutoRegistro`,
`FeatureFlagInteracaoTelaIAI` e `AuditoriaFluxoConfig`, e os services `customer_repository`, `template_engine`
e `behavioral_score`. Tem páginas HTML em `/app/`.

**Dependências entre apps:** `conversas` usa `context_agent_datadriven` (perfil, usuário real, proposta, t3,
roteiro) e `desafio_itau` (política, modelos, segredos). A app `recomendacao` não depende de nenhuma das outras.
**Não há `django.contrib.auth` nem `sessions`**: a sessão é o `sessao_id` guardado em SQLite.

---

## Etapa 4 — Pipeline de uma interação

Este é o caminho de `POST /api/v1/context-agent/conversas/interacao/`:

```
1 views_interacao.py      exige X-Sessao-Id → perfil_usuario.usuario_da_sessao (SQLite) → valida o JSON (≤ 8 KB)
2 interacao.interagir     etapa e escolha ∈ ETAPAS/BOTOES_VALIDOS
3                         extremos (regra) → fairness → domínio; se "fora", responde fixo e para aqui
4 coletar                 BigQuery em paralelo: perfil, mensal, proposta, subcategorias
                          (uma fonte que falha vira NAO_MEDIDO, nunca 0)
5 contexto_guard          confere o contexto antes de redigir
6 _guard_entrada          só para mensagem livre (input_guard no Gemini)
7 _gerar                  para cada modelo em MODELOS_GOOGLE: redige → interacao_avaliacao.avaliar
8 fallback                se nenhum modelo foi aprovado, usa texto_roteiro (também avaliado)
9 registro                ledger relatorios/avaliacoes/<data>.jsonl; histórico de 4 turnos livres (em memória)
10 resposta               200 schema 1.1 | 503 com texto:null, origem_resposta:"nenhuma"
```

A rota `conversas/mensagens/` segue o pipeline `ConversationService._pipeline`: extremos → input_guard →
`build_context` (BigQuery) → generate → guards → output_guard → release. Persiste em `conversas_sessao_cache`.

---

## Etapa 5 — Contrato HTTP

Não há autenticação nem streaming (sem SSE). A falta de medição aparece como `NAO_MEDIDO` / 503, nunca como zero.
O contrato detalhado para o front está em [docs/contrato-api-frontend.md](docs/contrato-api-frontend.md) e
[docs/rota-integrada-batalha-agentes-backend.md](docs/rota-integrada-batalha-agentes-backend.md).

**Montagem** (`desafio_itau/urls.py`): `context_agent_datadriven` responde em `/api/v1/context-agent/` **e** em
`/context-agent/`; `recomendacao` responde em `/api/v1/` **e** em `/app/`; `conversas` responde em
`/api/v1/context-agent/conversas/`. `GET|HEAD /healthz` devolve `{"status":"ok"}`, antes do CORS e da validação
de host.

### 5.1 Identidade e dados medidos — prefixo `/api/v1/context-agent/`

| Método e rota | Entrada | Saída principal | Erros |
| :--- | :--- | :--- | :--- |
| `POST perfil-usuario/definir/` | `{usuario: "1".."1000" \| UUID}` | 201 `{sessao_id, usuario{codigo,pessoa,genero,indice}, expira_em_segundos:14400}` | 400, 404, 503 `NAO_MEDIDO` |
| `POST perfil-usuario/pergunta/` | `{sessao_id, pergunta}` | 200 `{resposta, intencao, guard{estado,conferido}, modelo}` | 400, 404, 502 (guard reprovou), 503 |
| `GET\|POST i-agora/plano/proposta/` | `ref` (índice ou UUID), `data_corte?` | `{usuario, data_corte, estado, regra, segmento_t3, compromissos[], totais{…}, apresentacao, selos}` | 400 sem `ref`, 404, 503 |
| `GET usuario-real/<ref>/saldo-mes/` | `?data_corte=` | `{periodo{de,ate,rotulo}, entradas, saidas, saldo, negativado, media_mensal{…}, negativado_na_media, selo}` | 400, 404, 503 |
| `GET usuario-real/` · `<ref>/` · `<ref>/visao/<topico>/` · `status/` | paginação, `categoria`, `data_corte` | lista, perfil com visões, linha de visão com `sql_sha256`, status ON/OFF | 400, 404, 422 (fora do catálogo), 503 |
| `POST usuario-real/<ref>/pergunta/` | `{pergunta}` | responde a partir de uma visão, **sem LLM** | 400, 404, 503 |
| `GET controle-conversa/[?estagio=]` | — | roteiro `{versao, estagios, falas[], atraso_digitacao_ms}` | 400 estágio desconhecido |
| `POST primeira-chamada/` | `{texto_inicial}` | `{sucesso, modelo, resposta, tempo_resposta_ms}` | 400, 503 |
| `GET status-harness/[?validar=1]` | — | estado da chave: `AUSENTE`\|`CONFIGURADA`\|`VALIDADA`\|`INVALIDA`\|`NAO_MEDIDO` | — |
| `* enviar-mensagem/` | — | **410** `{erro:"rota_descontinuada", usar:".../conversas/interacao/"}` | — |

### 5.2 Conversa — prefixo `/api/v1/context-agent/conversas/`

| Método e rota | Entrada | Saída | Erros |
| :--- | :--- | :--- | :--- |
| `POST interacao/` | Header `X-Sessao-Id`. Corpo `{etapa, escolha?, mensagem?}`. Etapas: `home.visao_conta`, `bot.intro`, `intro.carrossel.1`, `bot.convite_50_30_20`, `bot.confirm`, `user.ajustar`, `bot.card`, `bot.finish`, `livre.respostas`. | 200 `schema_version "1.1"`: `texto`, `origem_resposta` (`modelo`\|`roteiro`\|`dados`\|`fairness`\|`guard_entrada`\|`fora_do_contexto`\|`encaminhamento`), `situacao`, `perfil_t3`, `fluxo`, `dados`, `selo`, `proximas_acoes[]`, `avaliacao{…}`, `encaminhamento` | 401/404 `sessao`, 400 `schema`/`etapa`, 405, 503 |
| `GET sessao/?sessao_id=` | — | `usuario`, `mode`. Grava os cookies `conversa_sessao` (httponly, 4 h) e `csrftoken`. | 404, 405 |
| `POST mensagens/` | Cookie ou `X-Sessao-Id`, **mais `X-CSRFToken`**. Corpo `{schema_version:"1.0", conversation_id, client_message_id, message}`. | `{status (ok\|needs_clarification\|safe_redirect\|unavailable), reply, citations[], contrato{…}}` | 400, 403, 404, 409, 429 (6/min, 20 turnos, 5 conversas), 503 |
| `GET status/` | — | modo, modelo, orçamento, limites, últimas chamadas | 405 |
| `GET avaliacoes/resumo/?data=AAAA-MM-DD` | — | resumo do ledger | 400, 405 |

### 5.3 Demo de recomendação — `/api/v1/` e `/app/`

`chave-interacao-tela-iai/` (GET/POST), `cliente/random/?genero=`, `cliente/<id>/`, `grupos-fixos/`,
`chat/variavel-1/<id>/`, `comunicacao/e-agora/<id>/`, `contexto-score/<id>/`, `planilha-fixa/`, e as páginas HTML
`/app/`, `/app/chat/<id>/`, `/app/comunicacao/<id>/`.

### 5.4 CORS e CSRF

- `CORS_ALLOWED_ORIGINS` é igual a `FRONT_ORIGENS`. `CORS_ALLOW_HEADERS` não foi alterado. Por isso **`X-Sessao-Id`
  não passa num preflight cross-origin**: as rotas que exigem esse header só funcionam na mesma origem (proxy do
  Vite ou front servido pelo próprio host).
- `CsrfViewMiddleware` **não** está em `MIDDLEWARE`, e as views são `APIView` do DRF sem autenticação. Por isso os
  POSTs de `context-agent/` aceitam requisições sem token. A exceção é `conversas/mensagens/`, que confere o
  `X-CSRFToken` por conta própria.

---

## Etapa 6 — Dados

| Fonte | O que é | Quem lê |
| :--- | :--- | :--- |
| BigQuery `batalha-time-02-lxof.hackathon_dados.extrato_sintetico` | Extrato sintético de 1.000 pessoas: fonte de todos os números mostrados | `usuario_real`, `plano_proposta`, `interacao_dados` (via ADC) |
| `data/usuarios_verdade.csv` (+ `.selo.json`) | Os 1.000 `id_usuario` com `indice`, `movimentos`, `meses`, `primeiro_anomes`, `ultimo_anomes`. `nome` e `genero` são inventados. | `perfil_usuario._carregar` |
| `db.sqlite3` | Sessões (`SessaoPerfilUsuario`), clientes demo, produtos, flag, cache de conversa. Local e no `.gitignore`. | Django |
| `init_database.py` | `migrate` e depois a população idempotente da demo: 1.000 clientes, 5 produtos, fluxo, chave ON | execução manual e Dockerfile |
| `datasets/` | Baterias ao vivo, corpus de intenção e amostras. **São evidência, não entram no runtime.** | testes e scripts |

Toda resposta com número carrega **selo**, com os campos `fonte`, `natureza_da_base: "sintetica"`, `autenticacao: "ADC"`,
`medido_em`, `jobs`, `bytes_processados` e `tempo_consulta_ms`.

---

## Etapa 7 — Encaixe com o front (verificação sistêmica)

Conferência feita em 2026-09-27 às 10:20 BRT, comparando o código do front (`frontend-agent-conversacional@main`)
com o código deste backend. As duas chamadas que o front faz estão cobertas pelo teste de contrato
[`tests/test_contrato_front_main.py`](tests/test_contrato_front_main.py). O teste percorre a resposta HTTP real
(com um executor BigQuery falso) e confere cada campo que o front lê sem fallback. Na prova negativa, o validador
tem de acusar um `totais.valor_liberado` ausente e um `nivel` fora de "Nível 1/2".

| Chamada do front | Rota aqui | Encaixe | Observação |
| :--- | :--- | :--- | :--- |
| `planApi.ts` `POST i-agora/plano/proposta/` `{ref: person.id+1}`, sem CSRF | `PlanoPropostaAPI` | **OK**, verificado no teste | Sem `CsrfViewMiddleware`, o POST sem token passa. Os estados `OK`/`LIVRE_SEM_CORTE`/`CORTE_INSUFICIENTE` coincidem com `ProposalState`. Em 503, o front mostra "Valores de exemplo (NAO_MEDIDO)". |
| `balanceApi.ts` `GET usuario-real/<ref>/saldo-mes/` | `UsuarioRealSaldoMesAPI` | **OK**, verificado no teste | O front usa só `negativado_na_media` e o saldo para a mensagem de apoio. Em 503 ou em `NAO_MEDIDO`, o front grava `saldoMedido = null`. |
| Texto livre no chat | `conversas/interacao/` \| `mensagens/` | **Não ligado** | O front responde localmente, por palavra-chave (`conversationService.replyTo`). |
| Identidade da pessoa | `perfil-usuario/definir/` | **Não ligado** | O front usa `ref = índice local + 1`, sem sessão. |
| Confirmar o plano / Acompanhe | `i-agora/plano/confirmar/`, `i-agora/acompanhamento/` | **Existe (2026-09-27)** | `apps/i_agora`. Confirmar exige o caso de compromisso preparado pela conversa (sem ele: 409); idempotente por `clientRequestId`. |
| Front i-agora (`Frontend/src/services/backend.ts`) | `conversas/sessao/`, `i-agora/perfil/`, `i-agora/plano/` GET/PATCH/DELETE, `plano/proposta/` POST/DELETE, `plano/confirmar/`, `sessao/abertura/`, `conversas/mensagens/` | **OK (2026-09-27)** | Portadas para `apps/i_agora`. `GET conversas/sessao/` sem sessão sorteia a pessoa entre os 1.000 do CSV da verdade; a mesma pessoa vale em `conversas/*` e `i-agora/*` até `sessao/abertura/ {next:true}`. `plano/proposta/` despacha pelo corpo: com `clientRequestId` é o contrato do front; com `ref` (ou GET) segue em `PlanoPropostaAPI`. Verificado: `tests/test_i_agora_*.py`. |

---

## Etapa 8 — Verificação

A suíte usa `unittest`: são 45 arquivos `tests/test_*.py`, sem pytest. Não há rede: o Gemini e o BigQuery
são simulados.

```powershell
# Use uma cópia do banco: sem SQLITE_PATH, a suíte grava sessões no db.sqlite3 real (backlog I10).
Copy-Item db.sqlite3 $env:TEMP\teste.sqlite3; $env:SQLITE_PATH="$env:TEMP\teste.sqlite3"
& $PY -m unittest discover -s tests
& $PY -m unittest tests.test_contrato_front_main -v     # encaixe com o front
```

| Medição | Valor | Fonte e hora |
| :--- | :--- | :--- |
| Suíte completa | **528 testes OK, 21 falhas esperadas** (`test_spec_*` e 1 limite do léxico) | `unittest discover`, 2026-09-27 10:15 BRT |
| Suíte completa após o porte do i-agora | **580 testes, OK** (1 skip, 22 falhas esperadas); antes do porte, na mesma árvore: 545 OK | `unittest discover -s tests` com `SQLITE_PATH` numa cópia, 2026-09-27 11:39 BRT |
| Contrato front ↔ back | **4/4 OK** | `tests.test_contrato_front_main`, 2026-09-27 10:21 BRT |
| Suíte completa após o contrato | **NAO_MEDIDO de forma estável**: entre 10:21 e 10:25, outra sessão editava `apps/conversas/*.py` e rodava a suíte em paralelo, e cada rodada deu um resultado diferente (falhas só em `test_conversas_*`). Rode de novo quando `apps/conversas` estiver parado. | 2026-09-27 10:25 BRT |

Efeito colateral conhecido: a suíte acrescenta linhas ao ledger `relatorios/avaliacoes/<data>.jsonl`, porque o
ledger não fica isolado nos testes.

---

## Etapa 9 — Limitações conhecidas

- As views `APIView` não têm autenticação. A identidade é um `sessao_id` com validade de 4 h, e o `ref` da
  proposta e do saldo é aceito sem sessão.
- `X-Sessao-Id` fica fora de `CORS_ALLOW_HEADERS`, o que obriga a servir na mesma origem (Etapa 5.4).
- O histórico de turnos livres e o orçamento `MAX_CHAMADAS` ficam **em memória do processo**. Com mais de um
  worker, cada um guarda os seus.
- `requirements.txt` traz `python-dotenv` e `jupyter`, que o runtime não usa. A imagem Docker instala tudo.
- A política em `desafio_itau/politica/` está com aprovação **PENDENTE**.
- As contagens de testes antigas nos docs (365, 346, 517) são de momentos anteriores. A contagem vigente está na
  Etapa 8.

---

## Etapa 10 — Mapa da documentação

| Documento | Para quê |
| :--- | :--- |
| [docs/INDICE.md](docs/INDICE.md) | Índice geral |
| [docs/architecture.md](docs/architecture.md) | Rotas, fluxos e limites em detalhe |
| [docs/contrato-api-frontend.md](docs/contrato-api-frontend.md) | Contrato para o front (§5.1–5.5) |
| [docs/rota-integrada-batalha-agentes-backend.md](docs/rota-integrada-batalha-agentes-backend.md) | Todas as rotas, com headers e erros |
| [docs/decisoes-e-logica-2026-09-27.md](docs/decisoes-e-logica-2026-09-27.md) | Decisões D-1…D-19 e Cloud Run (§5) |
| [docs/desenho-respostas-por-interacao.md](docs/desenho-respostas-por-interacao.md) | Desenho da rota `interacao/` |
| [docs/controle-da-conversa.md](docs/controle-da-conversa.md) | Roteiro de falas |
| [docs/backlog.md](docs/backlog.md) | Tarefas I1–I10 |
| [docs/rc8-rastreabilidade-2026-09-27.md](docs/rc8-rastreabilidade-2026-09-27.md) | Matriz da RC 8/2023 |
| [docs/estudo-i-agora/](docs/estudo-i-agora/INDICE.md) | SQL, T3, medições e schemas do estudo |
| [docs/inteirações-cloud/27-09-2026/](docs/inteirações-cloud/27-09-2026/INDICE.md) | JSON Schemas de envio e retorno |
| `archive/INDICE.md`, `docs/archive/INDICE.md` | O que saiu de uso, para onde foi e por quê (nada é apagado) |
