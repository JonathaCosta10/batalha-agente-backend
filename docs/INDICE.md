# Documentação do backend

| Documento | Conteúdo |
| --- | --- |
| [Controle da conversa](controle-da-conversa.md) | Todas as falas das telas com id, estágio, variáveis e fonte atual → alvo; rota `controle-conversa/`. |
| [Fluxo executado 2026-09-27](fluxo-executado-2026-09-27.md) | O que foi ligado (BigQuery, Gemini, proxy), caminho de uma requisição, medições ponta a ponta e pendências. |
| [Contrato da API para o front](contrato-api-frontend.md) | Como subir no local, conexões ON (BigQuery ADC, Gemini, SQLite, proxy), rotas do usuário real e integração em TS. |
| [Backlog](backlog.md) | Fluxograma ponta a ponta, controle de contexto, os pontos pedidos ligados ao código e as tasks (bug, demo, próximo, futuro), levantados em 2026-09-27 08:40. |
| [Arquitetura](architecture.md) | Rotas, fluxo de dados, primeira chamada, harness e limites observados. |
| [Fluxos de conversação](fluxos-de-conversacao.md) | Percurso das telas React, HTML Django e integração efetiva. |
| [Score comportamental](context_scoring.md) | Faixas do Ponto de Índice. |
| [Templates](templates/template_docs.md) | Regras e arquivos dos textos e da matriz de produtos. |
| [Contratos JSON Schema](inteirações-cloud/27-09-2026/INDICE.md) | Envios, retornos e formas da base de conhecimento. |
| [Qualidade da conversa](qualidade-conversa/INDICE.md) | Pergunta ao cliente 1, controles factuais, tempo medido e separação da base i.agora. |
| [Estudo i.agora](estudo-i-agora/INDICE.md) | Consultas e medições do extrato sintético BigQuery. |
| [Mudanças de semântica](CHANGELOG-semantica.md) | Contratos alterados em 2026-09-27: antes → depois e consumidor. |
| [Estudo i.agora](estudo-i-agora/INDICE.md) | Cópia do notebook, catálogo das consultas, SQL e medições seladas no BigQuery (ADC). |
| [Migração para política versionada](relatorio-migracao-politica-2026-09-27.md) | Relatório consolidado: o que saiu dos MDs, estados e contrato, testes, exemplos rastreáveis, limitações, pendências (COMPLETA / PARCIAL / NÃO FEITO) e tese. |
| [Rastreabilidade RC 8/2023](rc8-rastreabilidade-2026-09-27.md) | Dispositivo → obrigação → controle → teste → evidência → responsável (PENDENTE). Texto conferido com a API do BCB. |
| Política versionada (`desafio_itau/politica/`) | `operacional-v1.json` (limiares), `lexico-v1.json`, `erros_api-v1.json`, `comunicacao-v1.json`, `produtos-v1.json`; aprovação PENDENTE. |
| [Arquivo](archive/INDICE.md) | Versões anteriores preservadas nesta revisão. |
| Arquivo D-3 (`archive/2026-09-27/apps/context_agent_datadriven/`, `archive/2026-09-27/tests/`) | 2026-09-27: `enviar-mensagem/` passou a responder 410 Gone (usar `conversas/interacao/`). Saíram para o archive a view `EnviarMensagemHarnessAPI` + `validar_corpo_enviar_mensagem` (`views.py`), `ConversaAgenteSessao.despachar_chamada_harness` (`models.py`), `AgenteSecretService.enviar_mensagem_agente` (`services/agente_service.py`, sem chamador, chave na URL) e os testes do comportamento antigo (`test_semantica_backend.py` inteiro e a classe `EnviarMensagemTest` de `test_quatro_rotas.py`). `agentes/agente.py` e `google/cliente.py` ficam: outras rotas os importam. |
| [Rota integrada (backend)](rota-integrada-batalha-agentes-backend.md) | Todas as rotas com método, headers, corpo e erros; fluxo por etapa; dependências; publicado vs só local; divergências, levantado em 2026-09-27 09:02. |
| [Decisões D-1 a D-19 e lógica aplicada](decisoes-e-logica-2026-09-27.md) | Estado de cada decisão aceita às 09:28, lógica de metricas_fluxo.py com exemplos conferidos, as duas regras T3, o diagnóstico medido (D-2) e o levantamento do Cloud Run como etapa final (NÃO EXECUTADO), 2026-09-27. |
| Base de calibragem de comportamento (`desafio_itau/politica/comportamento.py`) | Schema, extrator e auditor (duplicados, perfil × contexto, limiares × `operacional-v1.json`, projeções R$, produto sem catálogo, léxico, marca) das perguntas e respostas do dono; `comportamento-v1.json` é gravado por `scripts/importar_comportamento.py <fonte>` (ainda NÃO importado, 2026-09-27 10:02). Não homologado; o chat não lê. Teste: `tests/test_base_comportamento.py`. |
| [Backend único e correções de integração](backend-unico-2026-09-27.md) | Um só backend na :8000 para o front; causas medidas do 502, da resposta "demo", da chave do Gemini, do 503 do guard de números (ponto decimal) e das rotas i-agora portadas do agent_backend; titular sorteado entre 1.000 e mantido até `next:true`; limites (429, timeout 15 s), 2026-09-27 11:50. |
| [Rotação dos modelos Gemini (raiz rotativa)](rotacao-modelos-gemini.md) | Chamadas por turno e tokens medidos, cota por modelo (painel 12:39) × papel, ordem por etapa em `cotas-gemini-v1.json` e como alterá-la, regras por erro, resfriamentos, RPM do processo, modelos excluídos, 2026-09-27 13:10. |

O README deste Git traz instalação e verificação. O front tem README e documentação próprios no repositório [agente-app-mobile](https://github.com/JonathaCosta10/agente-app-mobile).
