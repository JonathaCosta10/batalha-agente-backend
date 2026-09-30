# i.agora — backend Django (Time 2)

Backend da entrega do Time 2 na **Batalha de Agentes** (Itaú, 27/09/2026). Serve o front de
[batalha-agente-frontend](https://github.com/JonathaCosta10/batalha-agente-frontend): sorteia
uma pessoa da base, abre a sessão, conduz a conversa «i.ai» por etapas e devolve a frase de
abertura do botão **«E agora?»**.

## Prazo da entrega

A entrega do evento fechou no **domingo, 27/09/2026, às 11h00 (BRT)**. O que este repositório
tinha até essa hora é a entrega avaliada. **Tudo o que foi feito depois das 11h00 é trabalho de
desenvolvedor curioso**: consolidação, limpeza, créditos e este README, sem efeito no
resultado do evento.

## Resultado e classificação estimada

O time **não ficou entre os vencedores** (venceram os times 3, 5 e 11). Num estudo posterior
com o mesmo formulário aplicado aos 11 times a partir do código publicado, o Time 2 ficou em
**6.º ou 7.º lugar**: 29/35 na leitura de sete eixos (6.º) e 60,7/80 na leitura de cinco
eixos (7.º). Empate no topo em segurança e processo; menos pontos em dados, negócio,
arquitetura e engenharia. É uma estimativa pessoal do time, não o resultado oficial.

O que mais pesou, do lado do backend: o Gemini foi chamado por chave de API e devolveu 429 e
404 durante a demo, quando os vencedores usaram Vertex AI global com a service account do
projeto; e sem modelo a API respondia 503, sem roteiro degradado publicado.

## Os dois agentes

| Agente | Rota | O que faz |
|---|---|---|
| Identidade e perfil | `POST /api/v1/context-agent/perfil-usuario/definir/` | sorteia 1 de 1000 pessoas (`{"usuario":"aleatorio"}` ou por situação financeira), gera o nome com selo, abre sessão de 4 h; `perfil-usuario/pergunta/` responde só com o que a sessão sabe |
| Conversa «i.ai» | `POST /api/v1/conversas/interacao/` com `X-Sessao-Id` | uma fala por chamada, por etapa (`home.visao_conta`, `bot.intro`, `intro.carrossel.*`); `sessao/abertura/` devolve a abertura guiada; `avaliacoes/resumo/` expõe o ledger de guards |

Fluxo do front: `definir/` → `sessao/` (cookies `conversa_sessao` e `csrftoken`) → `interacao/`
→ `sessao/abertura/` → plano (`plano/proposta/`, `plano/rascunho/`, `plano/confirmar/`) →
`acompanhamento/`.

Cada turno passa por `input_guard` → `generate` → guards determinísticos de números e dados
pessoais → `output_guard`. O router por etapa está em `desafio_itau/politica/cotas-gemini-v1.json`:
guards em `gemini-3.1-flash-lite`, geração em `gemini-3.5-flash-lite`, reserva em
`gemini-flash-latest`; um 429 passa ao modelo seguinte. Prompts Liquid em
`apps/conversas/prompts/`. **O modelo não faz contas**: saldo e projeções vêm de
`apps/i_agora/` e de `apps/context_agent_datadriven/services/`.

## Apps

| App | Papel |
|---|---|
| `apps/context_agent_datadriven` | identidade, perfil, `usuario-real/*`, clientes LLM (`google` ativo; `antropic` e `openIa` são stubs), métricas de fluxo |
| `apps/conversas` | gateway do agente, roteador por etapa, guards, extremos, ledger de avaliações |
| `apps/i_agora` | sessão, abertura guiada, plano e acompanhamento |
| `apps/recomendacao` | recomendações a partir do extrato |
| `desafio_itau/` | settings, urls, política de modelos (`politica/`), `modelos_llm.py` |
| `data/` | `usuarios_verdade.csv` (1000 `id_usuario` do desafio, nome e género gerados por semente fixa) e o selo com o sha256 |
| `datasets/`, `scripts/` | extração do BigQuery, importação do comportamento (`importar_comportamento.py`), download da base |
| `skills/extracao-comportamental-iai` | skill de extração de comportamento usada nas medições |
| `tests/` | rotas, semântica, privacidade, quatro rotas de ponta a ponta |
| `CREDITOS.txt` | divisão medida do trabalho por autor e o registo do PR#4 |

## Como correr

```
python -m venv .venv && .venv\Scripts\activate      # Windows; no Linux: source .venv/bin/activate
pip install -r requirements.txt
python init_database.py                             # sqlite local e base de pessoas
python manage.py migrate
python manage.py runserver 8000
python -m pytest tests/                             # chave de teste falsa; sem chamadas reais
```

Segredos: `API_KEY_SECRECT` (chave Gemini) por variável de ambiente ou `.secrets`, nunca no
git. `IAGORA_HOSTS` e `IAGORA_DEV_ORIGINS` controlam hosts e CORS. Sem chave o gateway devolve
`erro_api` coerente e o front mostra o selo «modelo desligado». Deploy de demo: `Dockerfile`
com gunicorn, Cloud Run no projeto do desafio (serviço removido depois do evento).

## Autores

- **Jonatha Costa** — apps `conversas`, `i_agora` e `context_agent_datadriven`, identidade e
  sessão, integração com o front, consolidação.
- **Henrique França Carvalho Soares** — integração BigQuery e runtime Cloud Run, escolha do
  modelo, correções de valores, perguntas proativas e abertura guiada (portadas do
  `agent_backend` para `apps/i_agora`).

Detalhes medidos em `CREDITOS.txt`. Código lido e consolidado a 30/09/2026.
