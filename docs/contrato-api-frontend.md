# Contrato de conexão da API para o front

Contrato do backend Django para o front `frontend-agent-conversacional`. Os exemplos são respostas
reais. Foram medidos em **2026-09-27 às 05:17 BRT** pelo proxy do Vite
(`http://127.0.0.1:3001` → Django `127.0.0.1:8001`) contra o BigQuery `batalha-time-02-lxof`.
O acesso ao BigQuery usa ADC e a Gemini usa `API_KEY_SECRECT`.

Os esquemas JSON 2020-12 das rotas antigas estão em
[`inteirações-cloud/27-09-2026/`](inteirações-cloud/27-09-2026/INDICE.md). Este documento acrescenta
as rotas **usuário real** e reúne tudo o que o front precisa num só lugar.

---

## 1. Subir no local

Pasta raiz: `C:\Users\ACER\Desktop\hackton-1-itau\`. O venv com as dependências fica em
`frontend-agent-conversacional\.venv` (Python 3.12, Django 5.0.14, google-cloud-bigquery 3.45.2).

```powershell
# 1) Backend (na pasta backend-agente-conversacional)
$env:PYTHONPATH='.'; $env:PYTHONIOENCODING='utf-8'
..\frontend-agent-conversacional\.venv\Scripts\python.exe init_database.py        # idempotente
..\frontend-agent-conversacional\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000

# 2) Front (na pasta frontend-agent-conversacional)
npm run dev                                   # http://127.0.0.1:3000, proxy /api/v1 -> 8000
```

**Porta 8000 ocupada.** Em 2026-09-27 às 05:15, dois `runserver` de outro projeto
(`ROOT_URLCONF=config.urls`, iniciados a 26/09 22:38 e 23:00) ocupavam a porta 8000 e devolviam
404 em todas as rotas daqui. Nesse caso, suba o Django noutra porta e aponte o proxy com
`DJANGO_URL`:

```powershell
..\frontend-agent-conversacional\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
$env:DJANGO_URL='http://127.0.0.1:8001'; node node_modules/vite/bin/vite.js --port=3001 --host=127.0.0.1
```

### Conexões e como ficam ON

| Conexão | Como liga | Verificação | Estado medido 05:17 |
| --- | --- | --- | --- |
| Front → Django | proxy do Vite em `vite.config.ts`: **todo** `/api/v1` (antes só `/api/v1/context-agent`) | `GET /api/v1/cliente/928/` pelo 3001 | 200 |
| Django → BigQuery (usuário real) | ADC (`gcloud auth application-default login`, conta com acesso a `batalha-time-02-lxof`). `USUARIO_REAL['ATIVO']` é **ON** por padrão em `settings.py` | `GET .../usuario-real/status/?validar=1` → `conexao: VALIDADA` | VALIDADA, 1.000 usuários |
| Django → Gemini | `API_KEY_SECRECT`: env > `../.secrets` > **`../frontend-agent-conversacional/.secrets`** (este último caminho foi acrescentado hoje) | `GET .../status-harness/?validar=1` → `VALIDADA` | VALIDADA |
| Django → SQLite | `init_database.py` (migrações + 1.000 clientes demo + chave ON) | `GET /api/v1/chave-interacao-tela-iai/` | 200, `ON` |

Para desligar o usuário real, use `USUARIO_REAL_ATIVO=0`. As rotas respondem 503 com
`estado: "OFF"` e não fazem consulta. `USUARIO_REAL_CACHE_SEGUNDOS` define a validade do cache
(padrão: 900).

---

## 2. Duas fontes de "cliente": não misturar

| | **Cliente demo** (`/api/v1/cliente/...`) | **Usuário real** (`/api/v1/context-agent/usuario-real/...`) |
| --- | --- | --- |
| Origem | SQLite local e gerador determinístico | `hackathon_dados.extrato_sintetico` no BigQuery |
| Chave | `cliente_id` inteiro de 1 a 1000 | `id_usuario` UUID **ou** `indice` de 1 a 1000 (ordem de `id_usuario`) |
| Tem nome e gênero | sim, **inventados** (928 = "Eduarda Soares", F) | **não**: a tabela não tem nome nem gênero |
| Tem dinheiro | `saldo_estimado` e `score_comportamental` **fórmulas**, não medidos | inflow, outflow, surplus, dívidas, assinaturas: **somas do extrato** |

O `indice` 928 **não** é o cliente demo 928. Na tela, use `Cliente #<indice>` ou o nome demo marcado
como demo. Não atribua ao usuário real um nome que a base não tem. A tabela tem "sintético" no nome:
os dados são reais **da base do hackathon**, não de clientes do Itaú.

---

## 3. Convenções

- Base: `/api/v1/`. Sem autenticação. CORS restrito a `FRONT_ORIGENS` (localhost/127.0.0.1 nas portas 3000 e 3001; decisão D-5); `X-Sessao-Id` não está em `CORS_ALLOW_HEADERS`, por isso o front deve chamar pela mesma origem (proxy do Vite). É um protótipo local. *(corrigido 2026-09-27; antes dizia "CORS aberto")*
- JSON UTF-8. Valores em R$ saem como `number` com 2 casas. Percentuais saem em pontos (`56.71` = 56,71 %).
- Erro: `{"erro": "<texto>", "tempo_resposta_ms": <number>}`. As rotas de usuário real juntam
  `estado` quando a falha é da fonte.
- `tempo_resposta_ms` é medido **dentro** da view Django, sem contar a rede do navegador.
- `selo` acompanha todo número do BigQuery e diz de onde veio e quando foi medido:

```ts
type Selo = {
  fonte: string;                 // "batalha-time-02-lxof.hackathon_dados.extrato_sintetico"
  natureza_da_base: "sintetica";
  autenticacao: "ADC";
  medido_em: string;             // ISO BRT, ex. "2026-09-27T05:17:52-03:00"
  jobs: Record<string, string | null>;  // job_id do BigQuery por consulta
  bytes_processados: number;
  tempo_consulta_ms: number;
  cache: boolean;                // true = resposta do cache; medido_em é da medição original
};
```

### Códigos das rotas de usuário real

| HTTP | Quando | Corpo extra |
| --- | --- | --- |
| 200 | ok | — |
| 400 | referência não é inteiro nem UUID; `data_corte` fora de `AAAA-MM-DD`; `limite`/`offset` não inteiros; `pergunta` vazia | — |
| 404 | índice fora de 1..N; UUID inexistente na tabela | — |
| 422 | tópico fora do catálogo; categoria fora do mapa T3; pergunta sem tópico reconhecido | — |
| 503 | fonte desligada | `estado: "OFF"` |
| 503 | BigQuery falhou (sem ADC, rede, permissão, dry-run > 100 MB) | `estado: "NAO_MEDIDO"` |

Um 503 **não** traz número inventado. O front mostra "dados indisponíveis", não zero.

---

## 4. Usuário real (BigQuery)

Prefixo: `/api/v1/context-agent/usuario-real/`. Código:
[`services/usuario_real.py`](../apps/context_agent_datadriven/services/usuario_real.py) e
[`views_usuario_real.py`](../apps/context_agent_datadriven/views_usuario_real.py). SQL das visões:
[`pastas_raiz/estudos/i_agora/sql/`](../apps/context_agent_datadriven/pastas_raiz/estudos/i_agora/sql/).

**Janela:** meses completos antes do mês de `data_corte`. O padrão `2025-12-22` cobre jan-nov/2025, ou seja,
`meses_na_janela = 11`.

### 4.1 `GET status/` — ligar a tela

`?validar=1` faz uma consulta real, que é a lista e fica em cache. Sem esse parâmetro, a rota não usa a rede e
devolve `conexao: "NAO_MEDIDO"`.

```json
{
  "fonte": "usuario_real", "estado": "ON",
  "projeto": "batalha-time-02-lxof",
  "tabela": "batalha-time-02-lxof.hackathon_dados.extrato_sintetico",
  "data_corte_padrao": "2025-12-22", "cache_segundos": 900,
  "topicos": { "perfil_t3": "Inflow, Outflow, Surplus mensais, grupos de saída e segmento T3.", "categoria": "...", "renda": "...", "dividas": "...", "recorrencias": "...", "discricionario": "..." },
  "categorias": ["Assinaturas", "Boletos diversos", "Casa", "Cuidados pessoais", "Delivery", "..."],
  "conexao": "VALIDADA", "total_usuarios": 1000,
  "selo": { "...": "..." },
  "tempo_resposta_ms": 13744.9
}
```

`conexao`: `VALIDADA` | `FALHOU` (com `erro`) | `NAO_MEDIDO`. A **primeira** chamada fria levou
13,7 s porque cria o cliente BigQuery e roda a lista. Com cache, a lista respondeu em 66 ms.
Chame `status/?validar=1` ao abrir o app, antes do primeiro perfil.

### 4.2 `GET ?limite=20&offset=0` — lista paginada

`limite` vai de 1 a 1000 (padrão 20) e `offset` começa em 0.

```json
{
  "total": 1000, "limite": 3, "offset": 0,
  "usuarios": [
    { "indice": 1, "id_usuario": "00108ccd-699c-453a-a9f9-a66aad6e03e5", "movimentos": 433, "meses": 12, "primeiro_anomes": 202501, "ultimo_anomes": 202512 },
    { "indice": 2, "id_usuario": "001221d1-3626-45c1-807a-990502adf808", "movimentos": 750, "meses": 12, "primeiro_anomes": 202501, "ultimo_anomes": 202512 }
  ],
  "selo": { "...": "..." }
}
```

### 4.3 `GET <ref>/` — perfil completo (a chamada principal)

`<ref>` = `928` ou `ed943949-13b4-4bad-aa29-f55921487320` (maiúsculas aceitas). Opcional:
`?data_corte=AAAA-MM-DD`. Roda 5 visões em paralelo. Medido: **2,25 s** na primeira chamada,
**4 ms** com cache e ~192 MB processados no BigQuery.

```json
{
  "usuario": { "indice": 928, "id_usuario": "ed943949-13b4-4bad-aa29-f55921487320", "movimentos": 505, "meses": 12, "primeiro_anomes": 202501, "ultimo_anomes": 202512 },
  "data_corte": "2025-12-22",
  "janela": "meses completos antes do mês da data de corte",
  "resumo": {
    "segmento_t3": "Vulnerável",
    "inflow_mensal": 8828.12, "outflow_mensal": 10790.43,
    "surplus_mensal": -1962.31, "taxa_surplus_pct": -22.23,
    "meses_na_janela": 11, "saidas_sem_grupo": 0,
    "perfil_de_resposta": { "tom": "acolhedor e protetor", "foco": "compromisso financeiro: renegociar antes de cortar essencial" }
  },
  "visoes": {
    "perfil_t3": { "meses": 11, "inflow_mensal": 8828.12, "outflow_mensal": 10790.43, "surplus_mensal": -1962.31, "taxa_surplus_pct": -22.23, "essencial_mensal": 3983.87, "compromisso_mensal": 5006.58, "discricionario_mensal": 1664.13, "nao_classificado_mensal": 135.85, "saidas_sem_grupo": 0, "segmento_t3": "Vulnerável" },
    "renda": { "salario_clt_total": 62183.66, "recebimentos_diversos_total": 25512.03, "outras_entradas_total": 9413.62, "inflow_total": 97109.31, "inflow_mensal": 8828.12, "volatilidade_inflow_pct": 17.47, "meses": 11 },
    "dividas": { "compromisso_total": 55072.34, "compromisso_mensal": 5006.58, "fatura_total": 19244.07, "emprestimos_financiamentos_total": 34722.2, "juros_pagos_total": 475.37, "multas": 1, "lancamentos_parcelados": 24, "pct_inflow_comprometido": 56.71 },
    "recorrencias": { "lancamentos_assinaturas": 44, "assinaturas_total": 1204.17, "assinaturas_mensal": 109.47, "servicos_distintos": 4 },
    "discricionario": { "maior_categoria_discricionaria": "Lojas e sites", "maior_categoria_total": 11185.07, "discricionario_mensal": 1664.13, "categorias_discricionarias": 6 }
  },
  "sql_sha256": { "perfil_t3": "09a50f6b…", "renda": "1cfb1af1…", "dividas": "0a4a305e…", "recorrencias": "3e89014a…", "discricionario": "d10f9747…" },
  "selo": { "fonte": "batalha-time-02-lxof.hackathon_dados.extrato_sintetico", "natureza_da_base": "sintetica", "autenticacao": "ADC", "medido_em": "2026-09-27T05:17:52-03:00", "jobs": { "perfil_t3": "268a7711-9773-4d5a-8ae1-a38856489ae5", "...": "..." }, "bytes_processados": 192329813, "tempo_consulta_ms": 2220.2, "cache": false },
  "tempo_resposta_ms": 2220.362
}
```

Segmento T3, a regra de `t3.py`: `Livre` quando a sobra é ≥ 15 % do inflow. `Esbanjador` quando está
abaixo disso, mas cortar o discricionário a leva a ≥ 15 %. `Vulnerável` nos outros casos. O
`perfil_de_resposta` indica o tom que o texto da tela deve seguir para esse segmento.

### 4.4 `GET <ref>/visao/<topico>/` — uma visão

`topico` ∈ `perfil_t3 | categoria | renda | dividas | recorrencias | discricionario`.
`categoria` exige `?categoria=` com uma macro de `status.categorias`, sem diferenciar maiúsculas
nem acentos. A resposta devolve a grafia da base.

```json
{
  "usuario": { "indice": 928, "...": "..." }, "data_corte": "2025-12-22", "topico": "categoria",
  "parametros": { "id_usuario": "ed943949-…", "data_corte": "2025-12-22", "categoria": "Delivery" },
  "linha": { "categoria": "Delivery", "grupo": "discricionario", "lancamentos": 0, "total": 0.0, "media_mensal": 0.0, "pct_do_outflow": 0.0, "meses": 11 },
  "sql_sha256": "f74c9414…", "selo": { "...": "..." }, "tempo_resposta_ms": 1485.7
}
```

`lancamentos: 0` é **medido**: o usuário não teve Delivery na janela. É diferente de um 503.

### 4.5 `POST <ref>/pergunta/` — pergunta livre → números que a fundamentam

Corpo: `{"pergunta": "Quanto eu gasto com assinaturas?", "data_corte": "2025-12-22"?}`. Um roteador
por palavras-chave escolhe **uma** visão. A rota não chama LLM e devolve só os números
que um texto do agente pode usar. Sem tópico reconhecido, responde 422.

```json
{
  "pergunta": "Quanto eu gasto com assinaturas?", "categoria": "Assinaturas", "topico": "categoria",
  "linha": { "categoria": "Assinaturas", "grupo": "discricionario", "lancamentos": 44, "total": 1204.17, "media_mensal": 109.47, "pct_do_outflow": 1.01, "meses": 11 },
  "usuario": { "...": "..." }, "parametros": { "...": "..." }, "sql_sha256": "…", "selo": { "...": "..." }, "tempo_resposta_ms": 1426.7
}
```

### 4.6 `GET <ref>/saldo-mes/[?data_corte=]`: saldo do mês da linha de corte e média

Esta rota devolve entradas, saídas e saldo **do dia 1 do mês do corte até o corte, inclusive**, calculados por
`DATE(anomesdia)`. Ao lado vem a média mensal dos meses completos. O resultado fica em cache por 900 s. Se o
BigQuery falhar, a rota responde 503 `NAO_MEDIDO`.

```json
{
  "periodo": { "de": "2025-12-01", "ate": "2025-12-22", "rotulo": "até 22/12/2025" },
  "entradas": 9639.7, "saidas": 8567.59, "saldo": 1072.11, "lancamentos": 26,
  "negativado": false,
  "media_mensal": { "inflow_mensal": 8201.83, "outflow_mensal": 9931.45, "surplus_mensal": -1729.62, "meses_na_janela": 11 },
  "negativado_na_media": true,
  "usuario": { "...": "..." }, "data_corte": "2025-12-22", "selo": { "...": "..." }
}
```

Exemplo medido para o ref 1 em 2026-09-27 06:35:58 BRT, com 4,5 s a frio (fonte `extrato_sintetico`, ADC).
`negativado_na_media` vale `"NAO_MEDIDO"` quando não há média.

**Decisão do dono (2026-09-27 06:22):** a mensagem de apoio a negativados usa `negativado_na_media`. O número
mostrado no cartão da home ainda **não foi decidido** (ver [interacoes-front-back.md](interacoes-front-back.md) §1).

### 4.7 `POST i-agora/plano/proposta/` `{"ref", "data_corte"?}`: compromissos de janeiro

`GET ?ref=` responde o mesmo. A rota identifica o usuário por índice ou UUID, não por `sessao_id`, e
responde 400 quando falta o ref. A regra `corte_seguro_ate_surplus_15` está em
[controle-da-conversa.md](controle-da-conversa.md) §5a.

| Campo | Conteúdo |
| --- | --- |
| `estado` | `OK` · `LIVRE_SEM_CORTE` · `CORTE_INSUFICIENTE` |
| `compromissos[]` | `subcategoria` (grafia da tabela), `categoria_macro`, `nivel`, `gasto_atual`, `corte`, `meta`, `texto`, `raciocinio`, `ate_linha_de_corte` (número, ou `"NAO_MEDIDO"` se a consulta falhou) |
| `totais` | `inflow_mensal`, `surplus_mensal`, `necessario_para_surplus_15`, `valor_liberado`, `falta_apos_cortes`, `reserva` |
| `apresentacao` | `chave` ("subcategoria"), `linha_de_corte`, `base` {`inicio`, `fim`, `meses`}, `raciocinio[]`, `rodape` ("Com base nos seus registros até DD/MM/AAAA…"; nunca "projeção") |
| `selos` | `perfil`, `subcategorias`, `ate_linha_de_corte` |

Sem cache: cada chamada custa cerca de 3 consultas. Medido a frio: ~4 s. O gasto até o corte fica **fora** da
média.

### 4.8 `GET controle-conversa/[?estagio=]`: roteiro de falas

A rota devolve o `roteiro.json` validado (versão `2026-09-27.2`, 45 falas) e o lê a cada pedido: uma mudança
no arquivo vale na chamada seguinte. Um estágio desconhecido responde 400. O detalhe está em
[controle-da-conversa.md](controle-da-conversa.md).

---

## 5. Agente conversacional (Gemini)

Prefixo: `/api/v1/context-agent/`. Os esquemas estão em `inteirações-cloud/27-09-2026/`.

| Rota | Envio | Retorno 200 | Erros | Medido 05:17 |
| --- | --- | --- | --- | --- |
| `GET status-harness/[?validar=1]` | — | `llm_models_provedores.secret_gsconsole.status`: `AUSENTE`/`CONFIGURADA`/`VALIDADA`/`INVALIDA`/`NAO_MEDIDO` | — | 200, `VALIDADA`, 1,0 s |
| `POST primeira-chamada/` | **só** `{"texto_inicial": "..."}` (≤ 2000 caracteres; outra chave dá 400) | `{sucesso, modelo, resposta, tempo_resposta_ms}` | 400; 503 `{erro}` sem chave ou quando o modelo falha | 200, `gemini-3.5-flash-lite`, 2,2 s |
| `POST enviar-mensagem/` | **descontinuada (410), use `conversas/interacao/`** | — | 410 Gone para qualquer método, com JSON apontando a rota nova (Decisão D-3, 2026-09-27) | 410 (`tests/test_d3_rota_unica.py`) |

**Descontinuada (D-3, 2026-09-27):** `enviar-mensagem/` usava o **cliente demo** (com o usuário 928 chamou a
pessoa de "Eduarda") e responde 410 desde então. Use `perfil-usuario/definir/` e depois `conversas/interacao/` com o
header `X-Sessao-Id` (§5.1 e §5.3). O código antigo está em `archive/2026-09-27/`.

### 5.1 Perfil de usuário: "quem sou eu" (primeira chamada do front)

A **primeira chamada** do front define o usuário. A partir daí o backend sabe a quem responde.
A identidade vem do **CSV da verdade** `data/usuarios_verdade.csv`, gerado por
`scripts/baixar_usuarios_verdade.py`. Ele faz o DISTINCT de `id_usuario` no BigQuery (1.000 linhas,
job `657ffebb-09f9-49e2-abef-8dedbed639bb`, 2026-09-27T05:26 BRT) e junta `nome` e `genero` (F/M)
**sorteados**, com semente fixa. O índice 1 é fixado como Maria (F). O selo está em
`data/usuarios_verdade.selo.json`.

```ts
// 1) Ao abrir o app: define o usuário (índice 1..1000 ou id_usuario UUID)
POST /api/v1/context-agent/perfil-usuario/definir/   {"usuario": "1"}
// 201
{ sessao_id: string, expira_em_segundos: 14400,
  usuario: { codigo: string /* id_usuario */, pessoa: string /* "Maria" */, genero: "F" | "M", indice: number },
  tempo_resposta_ms: number }

// 2) Cada pergunta leva o sessao_id
POST /api/v1/context-agent/perfil-usuario/pergunta/  {"sessao_id": "...", "pergunta": "quem sou eu?"}
// 200
{ sessao_id, usuario, pergunta, intencao: "quem_sou_eu" | "nome" | "codigo" | "livre",
  resposta: string, modelo: string, origem_resposta: "modelo",
  guard: { estado: "APROVADO", conferido: ("pessoa" | "codigo")[] }, tempo_resposta_ms }
```

- **Código** = `usuario.codigo` e **pessoa** = `usuario.pessoa`. Esses dois campos saem do CSV, não do
  modelo. Use-os na tela. O texto de `resposta` é do Gemini.
- **Guard:** se a pergunta pede identidade, a `resposta` tem de trazer o nome e/ou o código exatos.
  Se não trouxer, o backend tenta o próximo modelo. Se nenhum passar, devolve
  **502** `{erro, guard: {estado: "REPROVADO", faltam}}`. Nesse caso, o front mostra os campos de `usuario`.
- **Erros:** 400 corpo inválido · 404 usuário inexistente, ou `sessao_id` desconhecido/expirado
  (chame `definir/` de novo) · 503 `estado: "NAO_MEDIDO"` sem o CSV · 503 quando nenhum modelo responde.
- A sessão fica **na memória do processo** Django: reiniciar o servidor apaga todas. O front, ao receber 404
  na pergunta, chama `definir/` de novo.
- Medido 2026-09-27 05:33 BRT: `definir/` 201 em 3 ms. `pergunta/` "quem sou eu?" 200 em 1,4 s, via
  `gemini-3.5-flash-lite`: "Olá, Maria! O seu código de identificação na Organizesee é
  00108ccd-699c-453a-a9f9-a66aad6e03e5. …", guard APROVADO. "qual o meu saldo?" 200: o modelo diz que
  ainda não tem essa informação.
- Testes: `python -m unittest tests.test_perfil_usuario` (12 testes, Gemini falso, com provas negativas).

### 5.2 Conversa i-agora: `conversas/sessao/` e `conversas/mensagens/` (front de agente-app-mobile)

Porte do `agent_backend/` de agente-app-mobile (commit `1302ba5`) para `apps/conversas/`. Prefixo:
`/api/v1/context-agent/conversas/`. O envelope é o **mesmo** `MessageResponse` 1.0 de
`src/types/conversation.ts` e as citações continuam só de `www.bcb.gov.br`/`www.itau.com.br`. Os campos
novos são aditivos: `usuario` no `sessao/` e `dados` nas respostas aprovadas.

A conversa fica presa ao `sessao_id` de **5.1**. O front passa esse `sessao_id` uma vez, no `GET sessao/`.

```ts
// 0) POST perfil-usuario/definir/ {"usuario": "1"} -> sessao_id  (5.1)
// 1) GET conversas/sessao/?sessao_id=<sessao_id>   (ou header X-Sessao-Id)
// 200 -> cookies: csrftoken + conversa_sessao (assinado, HttpOnly, SameSite=Lax, 4 h)
{ schema_version: "1.0", conversation_id: null, message_id, request_id, status, reply, citations: [],
  mode: "demo_live" | "demo",
  usuario: { codigo, pessoa, genero: "F" | "M", indice } }
// 2) POST conversas/mensagens/   headers: Content-Type: application/json, X-CSRFToken: <cookie csrftoken>
//    (X-Sessao-Id opcional; se vier, vale mais que o cookie)
{ schema_version: "1.0", conversation_id: string | null, client_message_id: string, message: string }
// 200
{ schema_version: "1.0", conversation_id, message_id, request_id,
  status: "ok" | "needs_clarification" | "safe_redirect" | "unavailable", reply, citations: Citation[],
  dados?: { estado: "MEDIDO" | "NAO_MEDIDO" | "OFF", selo: Selo | null } }
```

- O corpo do POST segue estrito, com `extra='forbid'`. `sessao_id` **não** pode ir no corpo, porque isso dá 400.
- `mode`: `demo_live` chama o Gemini. `demo` devolve um texto fixo, sem IA. O modo vem de
  `CONVERSAS_MODO` (padrão `demo_live`), e a tela mostra "TESTE Gemini · somente dados sintéticos".
- Identidade: o prompt de sistema recebe `pessoa`, `codigo` e `genero` do CSV da verdade. O gênero serve só
  para a concordância. Quando a pergunta pede identidade ("quem sou eu", nome, código), `perfil_usuario.conferir`
  exige o nome e/ou o código na resposta. Se faltar, a resposta sai do CSV, sem modelo.
- Números: os fatos do contexto vêm de `usuario_real.perfil(codigo)`: inflow, outflow, fluxo, essencial,
  compromisso, discricionário, assinaturas, segmento T3 etc. Cada número que o modelo cita tem de bater com o
  valor medido; se não bater, a resposta dá 503. Se o BigQuery falha: `dados.estado = "NAO_MEDIDO"`,
  nenhum número vai ao modelo, e nada vira zero.
- Chave e modelo: `obter_api_key()` e `modelos_llm.MODELO_PRIMEIRA_CHAMADA`. Cada mensagem gasta 3 chamadas:
  guard de entrada, gerador e guard de saída. O orçamento por processo é `CONVERSAS_MAX_CHAMADAS` (padrão 300).

| HTTP | Quando |
| --- | --- |
| 200 | ok, esclarecimento ou recusa segura (`status` diz qual) |
| 400 | corpo não-JSON, fora do schema, campo extra, > 16 KB |
| 403 | CSRF: sem `X-CSRFToken`, token errado ou `Origin` fora de `CSRF_TRUSTED_ORIGINS` |
| 404 | sem `sessao_id` válido (reply pede `perfil-usuario/definir/`); `conversation_id` de outra sessão ou expirada; caminho desconhecido |
| 405 | método errado |
| 409 | mesmo `client_message_id` com corpo diferente |
| 429 | limite: 6/min por sessão, 20 turnos, 5 conversas por sessão, pedido concorrente |
| 503 | provedor falhou ou resposta reprovada por um guard (texto seguro, sem detalhe) |

Todo erro vem no mesmo envelope, com `status: "unavailable"`.

**O front de agente-app-mobile precisa mudar:**
1. Antes de `bootstrap()`, chamar `POST /api/v1/context-agent/perfil-usuario/definir/`. Depois passar
   `?sessao_id=` na URL de `sessao/`, em `conversationApi.ts`. Com isso, o `send()` funciona sem mudança.
2. Apontar o proxy do `vite.config.ts` para a porta do Django (`8000` no padrão; o smoke usou `8012`).
3. Tratar 404 de `sessao/`/`mensagens/` como "definir usuário de novo". Desde 2026-09-27 (I4 / D-4) a sessão de
   usuário **e** a conversa sobrevivem ao reinício do processo; o 404 passa a significar sessão/conversa vencida
   (4 h) ou de outra sessão, não "o servidor reiniciou".
4. Opcional: mostrar `usuario.pessoa`/`usuario.codigo` do `sessao/` e o `dados.selo` junto da resposta.

**Persistência da conversa (I4 / D-4, 2026-09-27).** `ConversationService.sessions` passa a ser gravado no banco do
Django (cache com backend de banco, tabela `conversas_sessao_cache`, criada sob demanda; `apps/conversas/persistencia.py`).
Guarda só o que já ficava em memória: histórico **minimizado**, instante de criação e a proposta de projeção pendente.
Nada de prompt nem de contexto. TTL = `perfil_usuario.SESSAO_SEGUNDOS` (4 h), contado em relógio de parede e
aplicado na leitura. A chave carrega o `principal` (a sessão de usuário): outra sessão não enxerga a conversa (404).
Continuam só na memória do processo: rate limit (6/min), cache de idempotência (`client_message_id`) e bloqueio de
pedido concorrente. Nenhum campo do envelope mudou. Prova: `tests/test_fechamento_i4_i5_d15.py::ConversaPersistenteTest`.

Medido 2026-09-27 05:51 BRT (`runserver 8012`, usuário 1). `definir/` levou 0,01 s e `sessao/` 0,004 s.
"quem sou eu?" deu 200 em 15,2 s, frio, com BigQuery 2,5 s, 192 MB e 3 chamadas ao Gemini: "Você é Maria, e seu código
de identificação na base é 00108ccd-699c-453a-a9f9-a66aad6e03e5." "quanto eu gasto por mês?" deu 200 em 5,1 s,
com perfil em cache: "…suas saídas totais são de R$ 9.931,45 por mês, sendo R$ 4.582,53 de despesas
essenciais, R$ 3.901,34 de compromissos e R$ 1.048,85 de gastos discricionários." Os valores são iguais aos de
`GET usuario-real/1/`, e o selo é `extrato_sintetico` · ADC · `2026-09-27T05:51:20-03:00` · job perfil_t3
`2414a9b7-…`. Testes: `python -m unittest discover -s tests -p "test_conversas_*.py"` roda 64 testes, sem rede.

### 5.3 Interação por etapa: `POST conversas/interacao/` e `GET conversas/avaliacoes/resumo/`

Esta rota devolve uma fala por tela do front. A fala é redigida pelo Gemini sobre dados medidos e é avaliada em tempo de
execução. O desenho completo está em `docs/desenho-respostas-por-interacao.md`.

```
POST /api/v1/context-agent/conversas/interacao/
X-Sessao-Id: <sessao_id de POST perfil-usuario/definir/>        (obrigatório; 401 sem ele, 404 se expirou)
Content-Type: application/json                                    (até 8 KB)
{"etapa": "intro.carrossel.1", "escolha": "<id de botão>"?, "mensagem": "<texto livre>"?}
```

- **Etapas:** `home.visao_conta`, `bot.intro`, `intro.carrossel.1`, `bot.convite_50_30_20`, `bot.confirm`,
  `user.ajustar`, `bot.card`, `bot.finish`, `livre.respostas`. Uma etapa ou `escolha` desconhecida dá 400, com
  `etapas_validas`.
- **`mensagem`** é o texto livre do cliente e vale em qualquer etapa (`turno_livre: true`).
  - Uma pergunta fora do domínio financeiro recebe a resposta fixa `"Não faço ideia, sabia? Aí é que eu não sei."`, com
    `origem_resposta: "fora_do_contexto"`. Não chama o Gemini nem o BigQuery. **A redação ainda é provisória.**
- **200:**
  - `texto`
  - `origem_resposta`: `modelo` | `roteiro` | `dados` | `fairness` | `guard_entrada` | `fora_do_contexto`
  - `situacao` e `situacao_media`: `SOBROU` | `FALTOU` | `EQUILIBRIO` | `NAO_MEDIDO`
  - `mes_referencia`
  - `perfil_t3`
  - `fluxo`: `{id, versao, proximo_passo, regras}`
  - `cenario`: `{cenario: consolidacao_divida | inclinacao_gasto | financeiro_geral | fora_do_contexto, frases_obrigatorias, esqueleto, motivo, fatos}`
  - `dados` e `selo`: jobs do BigQuery
  - `estado_dados`
  - `regras_aplicadas`
  - `proximas_acoes`: `[{id, texto, etapa_seguinte, tipo}]`. Pode incluir `handoff.consolidacao`, de tipo `handoff_humano`;
    a rota de destino **NAO_IMPLEMENTADO**.
  - `avaliacao`: `{modelo, model_version, latencia_ms, tokens, aprovado, reprovados, checagens, tentativas, motivo_fallback, historico_turnos}`
    (`historico_turnos`, aditivo 2026-09-27: quantos turnos anteriores foram ao modelo, 0..4)
  - `aprovado`
  - `tempo_total_ms`
- **503:** traz o mesmo corpo com `texto: null` e `origem_resposta: "nenhuma"`. Acontece quando nem o modelo nem o texto do
  roteiro passam nos guards.
- **`schema_version` (D-15 / D9, 2026-09-27):** **`"1.1"` em toda resposta desta rota**: 200, 400, 401, 404, 405
  e 503. Antes os erros diziam `"1.0"`. O 200 já era `"1.1"` e é o contrato consumido, por isso o valor único é
  `"1.1"`. `GET conversas/avaliacoes/resumo/` e `conversas/mensagens/` (envelope `MessageResponse` 1.0) não mudam.
- **Histórico do turno livre (I5 / D-14, 2026-09-27):** o servidor guarda os **últimos 4 turnos livres** de cada
  `X-Sessao-Id` (mensagem minimizada + texto servido), em memória do processo, com o TTL da sessão (4 h). No turno
  livre seguinte eles vão ao modelo no bloco `HISTORICO_NAO_CONFIAVEL` (dado, não instrução: não mudam situação,
  fluxo, cenário, regras nem números) e ao input_guard como `history` (o gateway usa as 4 últimas entradas, ou seja,
  2 turnos). Extremo, fora do contexto, recusa do guard e contra-discurso **não** entram no histórico. Outra sessão
  nunca vê o histórico. O front não envia nada novo: basta repetir o mesmo `X-Sessao-Id`.
  Prova: `tests/test_fechamento_i4_i5_d15.py::HistoricoTurnoLivreTest` e o teste I5 de `tests/test_quatro_rotas.py`.
- **O front deve decidir a tela por `etapa` e `proximas_acoes`, nunca comparando texto.** O texto do Gemini muda a cada chamada.
- **Variável de ambiente:** `INTERACAO_GUARD_ENTRADA_MODELO=0` desliga o input_guard feito pelo modelo nos turnos livres.
  Cada chamada desse guard gasta 1 pedido da quota; com ele desligado, ficam o classificador de domínio e os guards de saída.
- **`GET conversas/avaliacoes/resumo/[?data=AAAA-MM-DD]`** lê o ledger `relatorios/avaliacoes/*.jsonl` e devolve:
  - respostas e taxas de aprovação;
  - latência p50/p95;
  - `reprovacoes_por_guard`;
  - contagens por modelo, etapa e origem.
  - Com o ledger vazio, devolve `NAO_MEDIDO`.
- **Medido (2026-09-27):**
  - Bateria de 30 exemplos ao vivo (`datasets/bateria-valor-2026-09-27.md`):
    - 16 chamadas do Gemini medidas, todas aprovadas na 1ª tentativa;
    - p50 de 1250 ms e p95 de 1566 ms;
    - 5 exemplos NAO_MEDIDO por quota (429).
  - O `gemini-flash-latest` deu 429 durante todo o dia.

### 5.4 Campos novos no envelope (aditivos, 2026-09-27): `contrato` e `erro_api`

Nenhum campo existente mudou. Um front que ignore os campos novos continua funcionando.

- **`conversas/mensagens/`: `contrato` (sempre presente)**
  - Valida em `ContratoRespostaV1` (`apps/conversas/schemas.py`). Campos (nomes exatos do código; correção D5): `schema_version` (`"1.0"`), `estado`, `periodo`, `evidence_ids`, `regras_aplicadas`, `acoes_permitidas`, `informacoes_faltantes`, `limitacoes_materiais`, `racional`.
  - `estado` assume um destes valores:
    - `ENCAMINHAMENTO`
    - `RECUSA_SEGURA`
    - `ESCLARECIMENTO`
    - `IDENTIFICACAO`
    - `DADOS_INSUFICIENTES`
    - `EDUCACAO_GERAL`
    - `ANALISE_DESCRITIVA`
    - `SIMULACAO`
    - `INDISPONIVEL`
  - `racional` é uma lista de `{observado, regra, consequencia}`. Nele aparecem só a regra pública e os números com fonte, sem raciocínio interno do modelo.
  - `regras_aplicadas` traz `rule_id@versao` de `desafio_itau/politica/operacional-v1.json` (aprovação **PENDENTE**).
  - **O front decide a tela por `contrato.estado` e `contrato.acoes_permitidas`, nunca pelo texto.**
- **`erro_api` (null só em sucesso; toda falha tem bloco desde a versão 1.1.0)**
  - Formato: `{codigo, tipo, nome, origem: api|provedor, acao_cliente, tentar_novamente_em_s, encaminhar_humano, mensagem, politica}`.
  - **Desde 1.2.0 (2026-09-27 13:03 BRT):** `codigo` é sempre número e `tipo` é sempre uma string estável, em
    `conversas/*` e `i-agora/*`. O HTTP da resposta segue o tipo: `cota_provedor` 429 (+ `Retry-After`),
    `timeout_provedor` 504, `provedor_indisponivel` 503, `resposta_reprovada_validacao` 503, `resposta_modelo_invalida` 503 (1.3.0: saída do modelo cortada/fora do schema em todos os modelos tentados). Antes, toda falha do
    provedor saía em HTTP 503. Tabela completa de tipos em
    [`backend-unico-2026-09-27.md`, "Códigos de erro para o front"](backend-unico-2026-09-27.md#códigos-de-erro-para-o-front-erros_api-130).
    A linha 400 do provedor passou a `resposta_segura` (sem nova chamada).
  - A tabela vem de `desafio_itau/politica/erros_api-v1.json` (1.2.0; a 1.1.0 está em `politica/archive/2026-09-27/`). Códigos com nova chamada ao modelo (400 deixou de ter na 1.2.0):

  | código | o servidor já fez | `acao_cliente` | espera sugerida | encaminhar |
  |---|---|---|---|---|
  | 400 | 1 nova chamada ao modelo alternativo | `reformular` | 0 s | não |
  | 404 | 1 nova chamada ao modelo alternativo | `reiniciar_sessao` | 0 s | não |
  | 429 | 1 nova chamada ao modelo alternativo, sem esperar | `aguardar_e_tentar_novamente` | 30 s | não |
  | 503 | espera ≤ 2 s e 1 nova chamada ao alternativo | `aguardar_ou_encaminhar` | 10 s | sim |
  | 504 (inclui timeout local) | 1 nova chamada ao alternativo | `aguardar_ou_encaminhar` | 15 s | sim |

  - Códigos só da nossa API (correção D6), sem nova chamada:

  | código | `acao_cliente` | o que o front faz |
  |---|---|---|
  | 401 | `reiniciar_sessao` | chama `perfil-usuario/definir/` de novo |
  | 403 | `nao_repetir` | a ação não está disponível; não repetir |
  | 405 | `nao_repetir` | erro de integração (método errado) |
  | 409 | `enviar_como_nova` | gera um novo `client_message_id` |

  - **`NAO_CLASSIFICADO`** (correção D7): status fora da tabela, exceção sem status, ou código que só vale para a API vindo do provedor. Exemplo: um 401 do Gemini é chave inválida, nunca "reinicie a sessão". Nesses casos o bloco sai com `nome: "NAO_CLASSIFICADO"`, o código real em `codigo` (null quando não havia), `acao_cliente: "aguardar_ou_encaminhar"` e a `origem` verdadeira. Antes, a falha do provedor sem tratamento saía rotulada como `origem: "api"`, código 503.
  - O servidor faz **no máximo 1** nova chamada e nunca repete o mesmo pedido ao mesmo modelo.
  - **Concorrência (correção D11):** o 429 de "pedido concorrente" vale **por usuário**. Antes, o bloqueio era global e um usuário podia receber o 429 do pedido de outro.
  - **Vida da conversa (correção D3):** o ttl da conversa passa a ser igual ao da sessão de usuário (4 h, `perfil_usuario.SESSAO_SEGUNDOS`), no lugar dos 30 min fixos. O cookie de 30 dias citado pelo front está no backend publicado (`agent_backend`), não neste repositório. Aqui, o cookie `conversa_sessao` já dura 4 h.
  - Se a nova chamada também falhar, sai o fallback técnico com `status: "unavailable"`.
  - Com `origem: "provedor"`, o código do Gemini vai em `erro_api.codigo`; o HTTP é 429/504/503 conforme o `tipo` (1.2.0; antes sempre 503).
  - `encaminhar_humano: true` só indica que o front pode oferecer esse caminho: a rota de handoff é **NAO_IMPLEMENTADO**.
- **`conversas/interacao/`**
  - Cada item de `avaliacao.tentativas` ganha `http_status` e `tratamento`.
  - Quando todas as tentativas falharam por erro de API, o corpo traz `erro_api` com o mesmo formato. Aqui não há nova chamada interna, porque o laço já percorre os modelos.
  - **Divergência D9: resolvida em 2026-09-27 (aprovação do dono, 09:41 BRT).** Toda resposta de `interacao/` sai com `schema_version: "1.1"`, erros incluídos (§5.3). Antes, o 200 saía com `"1.1"` e os erros com `"1.0"`. Front que lia `schema_version` só no 200 não muda.
  - **Persistência (I4) e histórico (I5):** ver §5.2 e §5.3. Nenhum campo do envelope mudou; `avaliacao.historico_turnos` é aditivo.

### 5.5 `GET conversas/status/`: estado do harness (2026-09-27)

Responde ao item 3 do pedido do front, na parte que cabe a este repositório. Sem texto, prompt ou identificador: as métricas saem por lista branca de campos.

```json
{"schema_version": "1.0", "modo": "demo_live",
 "modelo_configurado": "gemini-3.5-flash-lite", "modelo_guard": "gemini-3.5-flash-lite",
 "model_version_observado": "<modelVersion da última resposta do provedor> | NAO_MEDIDO (nenhuma chamada…)",
 "orcamento_processo": {"max_chamadas": 300, "usadas": 0, "restantes": 300},
 "cota_diaria_provedor": "NAO_MEDIDO: a API do Gemini não expõe a cota restante; o 429 é o sinal (erro_api)",
 "orcamento_diario": "NAO_IMPLEMENTADO: o teto é por processo (MAX_CHAMADAS), não por dia",
 "limites": {"pedidos_por_minuto_por_usuario": 6, "turnos_por_conversa": 20, "conversas_por_usuario": 5,
             "ttl_conversa_s": 14400, "timeout_s": 45, "novas_chamadas_max": 1, "espera_max_no_servidor_s": 2},
 "ultimas_chamadas": [{"stage", "model", "model_version", "latency_ms", "outcome", "total_tokens",
                       "nova_chamada", "tratamento_erro", "politica_operacional"}],
 "versoes": {"politica": "…@1.0.0", "lexico": "1.1.0", "erros_api": "…@1.1.0"}}
```

- **Modelo real:** é o `modelVersion` que o provedor devolveu, e não o nome gravado no código. `GET /api/health/` existe desde 2026-09-27 como alias leve do `/healthz` (`{"status":"ok"}`, sem chamar o provedor).
- **Aditivos 2026-09-27 (router):** `cota_diaria_esgotada`, `limites.timeout_por_etapa_s` e `roteador` = `{dados, ordem_por_etapa, ultimo_modelo_por_etapa, resfriamentos: {modelo: {restam_s, motivo}}, rpm_no_processo}` (null sem router). Qual modelo respondeu cada etapa: `roteador.ultimo_modelo_por_etapa` e `ultimas_chamadas[].model`.
- **Parcial:** não há orçamento por dia. As métricas vivem na memória do processo e zeram ao reiniciar; o ledger persistente é o de `interacao/`, em `relatorios/avaliacoes/`.

---

## 6. Cliente demo, telas e chave ON/OFF (SQLite)

Prefixo: `/api/v1/`. `cliente_id` fora de 1..1000 devolve 404 `{erro}` e não é trocado por outro id.

| Rota | Retorno | Medido 05:17 |
| --- | --- | --- |
| `GET cliente/<id>/` | `{id, nome, primeiro_nome, genero, grupo_fixo, score_comportamental, indice_corte, segmento, saldo_estimado, limite_cartao, diretriz_comportamental, tempo_relacionamento_meses, chave_pix_preferencial}` | 200 |
| `GET cliente/random/[?genero=F\|M]` | mesmo corpo | — |
| `GET chat/variavel-1/<id>/` | `{cliente:{id,nome,primeiro_nome,genero,grupo_fixo,score}, chave_interacao_tela_iai, modo_ativo, chat_variavel_1}` | 200 |
| `GET\|POST comunicacao/e-agora/<id>/` | payload do Template 3 (botão "E agora?") | 200 |
| `GET contexto-score/<id>/` | índice de corte e diretriz para o agente | 200 |
| `GET chave-interacao-tela-iai/` | `{codigo, nome, estado: "ON"\|"OFF", chave_ativa, comportamento, exemplos}` | 200, `ON` |
| `POST chave-interacao-tela-iai/` | corpo `{}` alterna; `{"chave_ativa": true\|false}` (boolean JSON; `"false"` texto dá 400) | — |
| `GET planilha-fixa/` | `{descricao, total_itens, itens}` | 200 |
| `GET grupos-fixos/` | estatísticas F/M e amostras | 200 |

---

## 7. Integração no front — mínimo para começar

```ts
// src/services/api.ts
const BASE = '/api/v1';

export class ApiErro extends Error {
  constructor(public status: number, public corpo: { erro: string; estado?: 'OFF' | 'NAO_MEDIDO' }) {
    super(corpo.erro);
  }
}

async function pedir<T>(caminho: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${caminho}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const corpo = await r.json();
  if (!r.ok) throw new ApiErro(r.status, corpo);
  return corpo as T;
}

export const usuarioReal = {
  status: () => pedir<{ estado: 'ON' | 'OFF'; conexao: string; total_usuarios?: number }>(
    '/context-agent/usuario-real/status/?validar=1'),
  listar: (limite = 20, offset = 0) =>
    pedir(`/context-agent/usuario-real/?limite=${limite}&offset=${offset}`),
  perfil: (ref: string | number) => pedir(`/context-agent/usuario-real/${ref}/`),
  visao: (ref: string | number, topico: string, categoria?: string) =>
    pedir(`/context-agent/usuario-real/${ref}/visao/${topico}/${categoria ? `?categoria=${encodeURIComponent(categoria)}` : ''}`),
  perguntar: (ref: string | number, pergunta: string) =>
    pedir(`/context-agent/usuario-real/${ref}/pergunta/`, { method: 'POST', body: JSON.stringify({ pergunta }) }),
};

export const agente = {
  primeiraChamada: (texto_inicial: string) =>
    pedir<{ sucesso: true; modelo: string; resposta: string }>('/context-agent/primeira-chamada/',
      { method: 'POST', body: JSON.stringify({ texto_inicial }) }),
};
```

Fluxo sugerido de telas:

1. Ao abrir o app, chamar `usuarioReal.status()`. Se vier `OFF`/`FALHOU`, mostrar "dados reais indisponíveis"
   e seguir no modo demo.
2. Escolher o usuário por lista, sorteio de índice 1..`total_usuarios` ou UUID fixo da demo.
3. Chamar `usuarioReal.perfil(ref)`. O `resumo.segmento_t3` e o `resumo.perfil_de_resposta` definem o tom
   da Tela 2. Os cartões mostram `visoes.*`, com o `selo.medido_em` visível ou disponível num tooltip.
4. No chat, chamar `usuarioReal.perguntar(ref, texto)` para obter o número. Para o texto
   conversacional, chamar `primeira-chamada` ou `enviar-mensagem`, que ainda não recebem os dados reais (ver §5).
5. Tratar `ApiErro.status === 503` como indisponível, **nunca** como zero.

---

## 8. O que não foi medido

- Cota e cobrança da chave Gemini: `VALIDADA` diz só que a Google aceitou a chave.
- Custo do BigQuery por sessão: cada perfil frio processa ~192 MB, e cada visão entre ~33 MB e ~38 MB. O limite
  por consulta é 100 MB (dry-run antes). O preço não foi calculado.
- Concorrência: foi testado um usuário por vez. O cache é por processo e se perde ao reiniciar o Django.
- Latência vista pelo navegador: `tempo_resposta_ms` é do servidor. Os tempos de 05:17 foram medidos pelo `curl` via proxy.

## 9. Verificação

```powershell
$env:PYTHONPATH='.'
..\frontend-agent-conversacional\.venv\Scripts\python.exe manage.py check
..\frontend-agent-conversacional\.venv\Scripts\python.exe -m unittest discover -s tests   # 93 OK em 2026-09-27
```

`tests/test_usuario_real.py` usa um executor falso, sem rede. Tem prova negativa para fonte OFF
(503, nenhuma consulta), índice ou UUID inexistente (404), referência lixo (400), tópico ou categoria fora
do catálogo (422) e BigQuery quebrado (503 `NAO_MEDIDO`, status `FALHOU`).
