# Fluxo executado em 2026-09-27 (05:11–05:45 BRT)

Este é o registro do que foi feito para ligar o backend ao usuário real e ao front, e de como cada peça se
comporta. Todos os números vêm de execuções desta data. O contrato de rotas está em
[contrato-api-frontend.md](contrato-api-frontend.md) e as falas estão em
[controle-da-conversa.md](controle-da-conversa.md).

## 1. Ponto de partida (medido às 05:11)

| Item | Estado encontrado |
| --- | --- |
| Pastas | `hackton-1-itau/` com `backend-agente-conversacional/` (sem `.git`), `frontend-agent-conversacional/` (sem `.git`) e `desafio-itau-batalha-de-agentes-time2/` (clone git de `github.com/JonathaCosta10/desafio-itau-batalha-de-agentes-time2`, `main`) |
| Chave Gemini | o backend procurava `hackton-1-itau/.secrets`, que não existe. A chave estava em `frontend-agent-conversacional/.secrets`. |
| BigQuery | ADC ativo (`gcloud`, projeto `batalha-time-02-lxof`). O código já tinha as visões por cliente, mas **nenhuma rota** as expunha. |
| Proxy do front | Vite repassava só `/api/v1/context-agent` para `127.0.0.1:8000`. |
| Porta 8000 | ocupada por dois `runserver` de **outro** projeto (`config.urls`, iniciados a 26/09 22:38 e 23:00), com 404 em todas as rotas daqui |
| Front | não faz nenhuma chamada de API. Tudo é fixo ou calculado no navegador (ver controle-da-conversa §1). |

## 2. Medição da base real (05:14, ADC)

- `hackathon_dados.extrato_sintetico` é a **única** tabela do dataset. Tem 467.585 linhas e as colunas
  `id_usuario` (UUID), `anomesdia`, `anomes`, `tipo` (E/S), `descr`, `vlr`, `nom_cate_macro`,
  `nom_cate_micro`, `saldo_apos`, `parcela_atual` e `parcela_total`.
- São 1.000 `id_usuario` distintos, com `anomes` de 202501 a 202512. A consulta levou 6,0 s.
- **Não há nome nem gênero** na base. "Usuário real" aqui quer dizer real **na base do hackathon**, cuja
  tabela se chama "sintético".

## 3. O que foi construído

| Passo | Arquivo | Comportamento |
| --- | --- | --- |
| Leitura do segredo | `desafio_itau/segredos.py` | Ordem de busca: `SECRETS_FILE` > `../.secrets` > `../frontend-agent-conversacional/.secrets`. A variável de ambiente `API_KEY_SECRECT` continua a ter precedência sobre qualquer arquivo. |
| Chave ON | `desafio_itau/settings.py` (`USUARIO_REAL`) | Ligada por padrão. `USUARIO_REAL_ATIVO=0` desliga, e aí as rotas dão 503 `estado: OFF` sem consultar o BigQuery. O cache vale 900 s. |
| Serviço | `services/usuario_real.py` | Lista os usuários (índice = `ROW_NUMBER() OVER (ORDER BY id_usuario)`), resolve índice ou UUID, roda as visões em paralelo e sela cada resposta (fonte, hora BRT, `job_id`, bytes). |
| Rotas | `views_usuario_real.py` | `status/`, lista, `<ref>/`, `<ref>/visao/<topico>/` e `<ref>/pergunta/`. |
| Proxy | `frontend-agent-conversacional/vite.config.ts` | Repassa todo `/api/v1`. O alvo pode ser trocado com `DJANGO_URL`. |
| Controle da conversa | `conversa/roteiro.json`, `views_controle_conversa.py` | 41 falas das telas com id, estágio, variáveis e fontes. A rota é `controle-conversa/`. |
| Testes | `tests/test_usuario_real.py`, `tests/test_controle_conversa.py` | Usam executor falso, sem rede, e têm provas negativas. |

Durante a sessão, **outra sessão** acrescentou `perfil-usuario/` (`services/perfil_usuario.py`,
`views_perfil_usuario.py`, `data/usuarios_verdade.csv` e `scripts/baixar_usuarios_verdade.py`). No CSV, o
índice 1 é "Maria". Essa parte não foi escrita nem revista aqui.

## 4. Caminho de uma requisição

```
navegador ──> Vite :3001 (proxy /api/v1, DJANGO_URL=http://127.0.0.1:8001)
          ──> Django :8001
               ├─ /api/v1/cliente|chat|comunicacao|contexto-score|chave-...  -> SQLite local (clientes demo)
               ├─ /api/v1/context-agent/primeira-chamada|enviar-mensagem     -> Gemini (API_KEY_SECRECT)
               ├─ /api/v1/context-agent/usuario-real/...                     -> BigQuery (ADC), cache 900 s
               └─ /api/v1/context-agent/controle-conversa/                   -> roteiro.json
```

Uma chamada de perfil passa por estas etapas:

1. `resolver(ref)` usa a lista em cache. Um índice fora de 1..1000 ou um UUID ausente dá 404; lixo dá 400.
2. As cinco visões (`perfil_t3`, `renda`, `dividas`, `recorrencias`, `discricionario`) rodam em
   paralelo. Cada uma faz um **dry-run** antes e recusa acima de 100 MB.
3. O Surplus e o T3 (`Livre` ≥ 15 %; `Esbanjador` quando cortar o discricionário devolve os 15 %;
   `Vulnerável` nos outros casos) são calculados **no SQL**. O Python só monta o resumo e o tom de
   resposta.
4. A resposta vai com o selo e é guardada em cache por (UUID, data de corte).

## 5. Verificação ponta a ponta (05:17, pelo proxy 3001)

| Rota | HTTP | Tempo |
| --- | --- | --- |
| `usuario-real/status/?validar=1` (frio) | 200, `VALIDADA`, 1.000 | 13,7 s |
| `usuario-real/?limite=3` | 200 | 0,07 s |
| `usuario-real/928/` (frio / cache) | 200 / 200 `cache:true` | 2,25 s / 0,004 s |
| `usuario-real/928/visao/categoria/?categoria=Delivery` | 200, 0 lançamentos | 1,49 s |
| `usuario-real/928/pergunta/` "assinaturas" | 200, categoria Assinaturas, R$ 1.204,17 | 1,43 s |
| `usuario-real/1001/` · `visao/horoscopo/` | 404 · 422 | < 0,01 s |
| `status-harness/?validar=1` | 200, `VALIDADA` | 1,03 s |
| `primeira-chamada/` | 200, `gemini-3.5-flash-lite` | 2,20 s |
| `enviar-mensagem/` (cliente 928) | 200, `origem_resposta: modelo` | 3,53 s |
| `cliente/928`, `chat/variavel-1/928`, `comunicacao/e-agora/928`, `contexto-score/928`, `chave-interacao-tela-iai`, `planilha-fixa`, `grupos-fixos` | 200 | < 0,01 s |

Resultado do usuário 928 (UUID `ed943949-…`, janela jan–nov/2025, selo 05:17:52):

- Segmento **Vulnerável**.
- Inflow R$ 8.828,12/mês e outflow R$ 10.790,43/mês, o que dá surplus de −R$ 1.962,31 (−22,23 %).
- Compromisso financeiro: 56,71 % do inflow.

Suíte: **109 testes OK** às 05:40. Nesse número entram os testes da outra sessão (`test_perfil_usuario.py`).

## 6. Comportamentos que o front precisa conhecer

- **503 não é zero.** `estado: "OFF"` indica fonte desligada e `estado: "NAO_MEDIDO"` indica BigQuery
  indisponível. Nos dois casos não sai número.
- **`lancamentos: 0` é medido.** O usuário não teve lançamentos naquela categoria.
- **O cache devolve o selo original.** `medido_em` é a hora da consulta, não a da resposta, e `cache: true`
  sinaliza que veio do cache.
- **A primeira chamada é lenta** (~14 s) porque cria o cliente BigQuery e roda a lista. Aqueça com
  `status/?validar=1` ao abrir o app.
- **Os valores são médias mensais de jan–nov/2025.** Dezembro é excluído porque o corte da tese é 22/12 e
  o mês ficaria parcial.
- **`enviar-mensagem` ainda fala com o cliente demo.** Com 928, a resposta chamou a pessoa de "Eduarda".
  Os números reais ainda não chegam ao prompt.
- **O índice do usuário real não é o `cliente_id` demo.**

## 7. O que ficou por fazer ou bloqueado

| Item | Situação |
| --- | --- |
| Commit e push | **Feito** depois do "pode fazer" do dono. Os commits `172d246`, `76d6ab0`, `4e8947f`, `f2752b5`, `7487d04`, `424ae27` e `e550d80` estão em origin/main. Só entrou trabalho da back-25 e o texto revisto das outras sessões no doc conjunto. As rotas da back-32 (perfil-usuario, conversas) ainda estão fora deste git. |
| Front consumir API | **parcial**: saldo-mes (decisão de negativado) e plano/proposta já estão ligados no front (mobile-front-agente 793b96b/2835401); controle-conversa ainda não |
| Cartão "Visão da conta" da home | mostra números sintéticos, sem selo; o dono tem de escolher saldo-mes.saldo ou media_mensal |
| Modelo gemini-3.8-flash | o dono pediu para usá-lo. Medido às 06:12: 429, quota do plano gratuito de 20 pedidos/dia por modelo. O modelo em uso continua `gemini-3.5-flash-lite` |
| Chave Gemini no cofre do hub e aviso ao blog | **bloqueado pelo classificador de permissões**: a gravação do valor em `_dados-locais/secrets/.env.compartilhado` foi negada. O valor tem de ser colocado pelo dono |
| Mover o backend para agente-app-mobile | negado pelo classificador (cópia entre repositórios); o dono decidiu "agora não" |
| Falas preenchidas por usuário (`controle-conversa/<ref>/`) | proposto em controle-da-conversa §6 |
| Números reais no prompt do `enviar-mensagem` com o guard | proposto |
| Custo do BigQuery | NAO_MEDIDO: ~192 MB por perfil frio, preço não calculado |

## 8. Como repetir

```powershell
cd C:\Users\ACER\Desktop\hackton-1-itau\backend-agente-conversacional
$env:PYTHONPATH='.'; $env:PYTHONIOENCODING='utf-8'
..\frontend-agent-conversacional\.venv\Scripts\python.exe -m unittest discover -s tests
..\frontend-agent-conversacional\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
# outro terminal, na pasta do front:
$env:DJANGO_URL='http://127.0.0.1:8001'; node node_modules/vite/bin/vite.js --port=3001 --host=127.0.0.1
curl "http://127.0.0.1:3001/api/v1/context-agent/usuario-real/status/?validar=1"
curl "http://127.0.0.1:3001/api/v1/context-agent/controle-conversa/?estagio=card"
```
