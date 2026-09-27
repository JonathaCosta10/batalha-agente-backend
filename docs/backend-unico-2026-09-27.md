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

## 5. Limites conhecidos (não resolvidos aqui)

- **Cota do Gemini (429):** a chave é partilhada; com mais de um processo a chamar (ex.: validação noutra porta), o
  provedor devolve 429 e a conversa responde 503 com `erro_api.codigo=429` e `tentar_novamente_em_s=30`. É o sinal
  previsto pela política de erros, não defeito do backend.
- **Timeout de 15 s** por chamada ao provedor (`apps/conversas/gateway.py`, `TIMEOUT_SEGUNDOS`); acima disso tenta o
  modelo alternativo. Em pico o `generate` estoura os 15 s.
- Caminho de compromisso com o Gemini real não verificado (só com gateway falso nos testes).
- Mês de corte do plano segue o mês atual (como o `agent_backend`), não o `DATA_CORTE` do backend.
- `GCSPlanStore` e `admit_call` do `agent_backend` não foram portados.
