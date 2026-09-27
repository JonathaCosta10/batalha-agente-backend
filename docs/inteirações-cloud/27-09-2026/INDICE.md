# Contratos JSON Schema — 27-09-2026

Formas derivadas do código em 2026-09-27; campo marcado `NAO_VERIFICADO` na description quando a forma não pôde ser confirmada.

Todos em JSON Schema draft 2020-12. Caminhos de código relativos à raiz do projeto Django.

| Contrato | Endpoint / fonte | Ficheiro | Origem no código (ficheiro:linha) |
|---|---|---|---|
| Primeira chamada: envio | `POST /api/v1/context-agent/primeira-chamada/` | `padrao-envio.json` | `apps/context_agent_datadriven/views.py:117-128` |
| Primeira chamada: retorno | `POST /api/v1/context-agent/primeira-chamada/` | `padrao-retorno.json` | `apps/context_agent_datadriven/views.py:130-133`; `apps/context_agent_datadriven/services/primeira_chamada.py:13-40` |
| Enviar mensagem: envio | `POST /api/v1/context-agent/enviar-mensagem/` | `enviar-mensagem/padrao-envio.json` | `apps/context_agent_datadriven/views.py:67-81` |
| Enviar mensagem: retorno | `POST /api/v1/context-agent/enviar-mensagem/` | `enviar-mensagem/padrao-retorno.json` | `apps/context_agent_datadriven/views.py:99-109`; `apps/context_agent_datadriven/agentes/agente.py:132-152`; `apps/context_agent_datadriven/pastas_raiz/controles_evals/evals_google_agent.py:35-45` |
| Chat variável 1: retorno | `GET /api/v1/chat/variavel-1/<cliente_id>/` | `chat-variavel-1/padrao-retorno.json` | `apps/recomendacao/views.py:121-140`; `apps/recomendacao/services/template_engine.py:127-187`; `apps/recomendacao/services/customer_repository.py:37-93` |
| E agora?: retorno | `GET` e `POST /api/v1/comunicacao/e-agora/<cliente_id>/` | `e-agora/padrao-retorno.json` | `apps/recomendacao/views.py:148-158`; `apps/recomendacao/services/template_engine.py:190-232`; `apps/recomendacao/services/behavioral_score.py:16-65` |
| Chave inteiração-tela-iai: envio | `POST /api/v1/chave-interacao-tela-iai/` | `chave-interacao-tela-iai/padrao-envio.json` | `apps/recomendacao/views.py:52-59` |
| Chave inteiração-tela-iai: retorno (GET e POST, `oneOf`) | `GET` e `POST /api/v1/chave-interacao-tela-iai/` | `chave-interacao-tela-iai/padrao-retorno.json` | `apps/recomendacao/views.py:30-50` (GET), `:61-67` (POST); `apps/recomendacao/services/template_engine.py:87-124` |
| Status do Harness: retorno | `GET /api/v1/context-agent/status-harness/` | `status-harness/padrao-retorno.json` | `apps/context_agent_datadriven/views.py:28-57`; `apps/context_agent_datadriven/services/agente_service.py:37-53` |
| Base de rotas | `rotas/templates/rotas_base.yaml` e `BaseDeRotasManager.carregar_rotas()` | `knowledge/rotas-base.schema.json` | `apps/context_agent_datadriven/rotas/templates/rotas_base.yaml:7-75`; `apps/context_agent_datadriven/rotas/manager.py:10-97` |
| Tese do agente | `TESE_COMPLETA_CONTEXTUALIZADA` | `knowledge/tese-agente.schema.json` | `apps/context_agent_datadriven/pastas_raiz/docs/tese_agente_docs.py:6-25` |
| Métricas de eval | `EVAL_METRICAS_MERCADO` | `knowledge/evals.schema.json` | `apps/context_agent_datadriven/pastas_raiz/controles_evals/evals_google_agent.py:12-33` |

## Avisos que os contratos registam

- `enviar-mensagem`: sem resposta do Google, devolve HTTP 503, `sucesso: false`, `origem_resposta: contingencia` e texto local rotulado. `groundedness_score` é `null` e `eval_status` é `NAO_MEDIDO` quando não há comparação com evidências. `REPROVADO_VAZAMENTO` bloqueia a resposta reprovada, substitui o texto por mensagem segura e não grava o par na sessão. `tempo_resposta_ms` mede a view Django.
- `primeira-chamada`: `tempo_resposta_ms` mede a view Django, inclusive nas respostas 400 e 503. Não representa tempo de rede do navegador.
- `enviar-mensagem`: o `db.sqlite3` anterior às migrações foi observado com **HTTP 500** em 2026-09-27 por falta de colunas de sessão/mensagem. A instalação nova usa as migrações Django executadas por `init_database.py`.
- `status-harness`: sem `?validar=1`, `CONFIGURADA` só indica presença da chave. Com o parâmetro, `VALIDADA`/`INVALIDA` vêm de uma consulta à Google; `NAO_MEDIDO` informa falha de medição. Nenhum estado mede cota do projeto.
- `rotas_base.yaml` não é lido de verdade: `parse_simple_yaml` devolve um dicionário fixo no código, que não tem `segmentos_prioritarios`.
- `chave-interacao-tela-iai` POST: campo ausente alterna; campo presente exige JSON boolean. `"false"` (texto) e `null` devolvem HTTP 400. Falha de gravação devolve HTTP 500, sem afirmar sucesso.
- IDs de cliente fora de 1..1000 devolvem HTTP 404 nas rotas de cliente, chat, comunicação e score; não são convertidos para outro cliente.
