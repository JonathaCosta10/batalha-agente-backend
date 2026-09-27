# desafio-itau-batalha-de-agentes-time2

Backend **Django + Django REST Framework** da demonstração Batalha de Agentes
Itaú. Este Git é separado do front Node `agente-app-mobile`. Ele serve páginas
HTML próprias, APIs de recomendação e dois fluxos distintos de agente.

## Início rápido

Na pasta deste repositório, com Python 3.12:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe init_database.py
.venv\Scripts\python.exe manage.py runserver 8000
```

Abra `http://127.0.0.1:8000/`: a raiz redireciona para `/app/`. As APIs ficam
sob `/api/v1/`. Os perfis de clientes têm geração determinística quando a base
SQLite não foi populada. Para criar as tabelas e os 1.000 registros de
recomendação em `db.sqlite3`, execute `init_database.py`: ele aplica as migrações
Django e popula o fluxo, os clientes, os cinco produtos e a chave ON/OFF. Esse
arquivo SQLite é local e está no `.gitignore`.

## Chave Google da primeira chamada

O front chama `POST /api/v1/context-agent/primeira-chamada/`. Essa rota envia
somente o texto inicial ao modelo `gemini-3.5-flash-lite`; não envia histórico,
score nem perfil. A chave é lida no servidor por
[`desafio_itau/segredos.py`](desafio_itau/segredos.py), nesta ordem:

1. Variável de ambiente `API_KEY_SECRECT` (grafia preservada do código).
2. `API_KEY_SECRECT` em `.secrets` na pasta **pai** deste repositório, ao lado
   do `package.json` do front. `SECRETS_FILE` permite outro caminho.
3. Variáveis legadas `GEMINI_API_KEY`, `GSCONSOLE_SECRET`, `GOOGLE_API_KEY`.

Para um teste local sem arquivo de segredo, defina a variável no mesmo terminal
que inicia o Django:

```powershell
$env:API_KEY_SECRECT = 'chave-do-projeto-google-com-cota'
.venv\Scripts\python.exe manage.py runserver 8000
```

O contrato é `{"texto_inicial":"..."}`; sucesso retorna `sucesso`, `modelo` e
`resposta`. Entrada inválida devolve HTTP 400; falta de chave ou falha do
provedor devolve HTTP 503 com `erro`. Os esquemas JSON estão em
[`docs/inteirações-cloud/27-09-2026/`](docs/inteirações-cloud/27-09-2026/INDICE.md).
`GET /api/v1/context-agent/status-harness/` informa `AUSENTE` ou `CONFIGURADA`
sem chamada externa. Com `?validar=1`, faz uma validação contra a Google e
informa `VALIDADA`, `INVALIDA` ou `NAO_MEDIDO`; isso ainda não mede a cota do
projeto. O painel HTML mostra somente o estado local.

## Usuário real (BigQuery) e contrato do front

As rotas em `/api/v1/context-agent/usuario-real/` leem os 1.000 `id_usuario` do extrato no
BigQuery via ADC. Elas devolvem o perfil T3, a renda, as dívidas, as assinaturas e o discricionário, sempre
com selo de fonte, job e hora. Essas rotas ficam ligadas por padrão e `USUARIO_REAL_ATIVO=0` as desliga.
Contrato completo para o front: [docs/contrato-api-frontend.md](docs/contrato-api-frontend.md).

A conversa i-agora (`apps/conversas/`, porte de agente-app-mobile) responde em `/api/v1/context-agent/conversas/`
(`sessao/?sessao_id=` e `mensagens/`), com o `sessao_id` de `perfil-usuario/definir/` e os números do usuário real com selo. Ver a seção 5.2 do contrato.

## Componentes e rotas

| Componente | Responsabilidade |
| --- | --- |
| [`apps/recomendacao/`](apps/recomendacao/) | Perfis por ID, score, Variável 1, Template 3, páginas HTML e APIs equivalentes. |
| [`apps/context_agent_datadriven/`](apps/context_agent_datadriven/) | Primeira chamada Gemini, status e fluxo contextualizado com sessão. |
| [`desafio_itau/urls.py`](desafio_itau/urls.py) | Monta `/app/`, `/api/v1/` e `/context-agent/`. |
| [`init_database.py`](init_database.py) | Aplica `migrate` e popula (idempotente) produtos, a chave ON e os 1.000 clientes no SQLite local. |
| [`docs/architecture.md`](docs/architecture.md) | Fluxos de execução, persistência e limites comprovados no código. |

O endpoint `enviar-mensagem` é diferente de `primeira-chamada`: cria/usa sessão
Django, seleciona categoria e envia prompt de sistema e histórico. Depende de
tabelas de sessão Django criadas pelas migrações do projeto. Se nenhum modelo
responder, devolve HTTP 503, `sucesso: false` e `origem_resposta: contingencia`,
com um texto local identificado como tal. O front atual não usa esse endpoint.

O [índice da documentação](docs/INDICE.md) reúne a arquitetura, os fluxos e os
contratos de cada rota.

As duas rotas de conversa devolvem `tempo_resposta_ms` medido dentro da view
Django. O `eval_harness` declara `groundedness_score: null` e `NAO_MEDIDO`
enquanto não houver comparação da resposta com fatos recuperados da base.

## Estudo i.agora, T3 e guard

O estudo mede a base sintética no BigQuery (`batalha-time-02-lxof`, autenticação ADC,
sem chave) e sela cada número com fonte, job e hora BRT. A segmentação T3
(Vulnerável, Esbanjador, Livre) sai de Inflow, Outflow e Surplus. O guard refaz o
SELECT da visão e compara os valores normalizados com os que o agente enviou. A
leitura completa, com os limites medidos, está em
[t3-e-resposta.md](docs/estudo-i-agora/t3-e-resposta.md) e no
[índice do estudo](docs/estudo-i-agora/INDICE.md).

## Controles internos do chatbot

Os controles da solução ficam no código do projeto: as visões e o guard factual
do estudo i.agora em `apps/context_agent_datadriven/pastas_raiz/estudos/i_agora/`,
os contratos de API em `docs/inteirações-cloud/` e a
[skill de extração IAI](skills/extracao-comportamental-iai/SKILL.md), que sorteia
uma linha do extrato e valida a proposta antes de publicar o texto. O fluxo
atual do botão ainda não executa essa skill.

`.claude/` é material local de desenvolvimento pessoal, ignorado pelo Git.

## Revisão independente pelo Gemini

```powershell
..\.venv\Scripts\python.exe scripts\revisao_gemini.py --titulo "<pedido>" <arquivos...>
```

O script envia os arquivos ao `gemini-2.5-flash-lite` como revisor. Ele grava
`relatorios/revisao-gemini/<data>.json` com o sha256 de cada arquivo e o tempo
medido. O veredito do Gemini é uma opinião a conferir, não uma aprovação. Sem
chave em `.secrets`, o script responde `NAO_MEDIDO` e não grava nada. Esse é o
estado em 2026-09-27.

## Verificação

```powershell
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe -m unittest discover -s tests -p test_primeira_chamada.py -v
```

Esses testes simulam a resposta Google e verificam a carga de texto, a ordem
de leitura da chave e a ausência de chamada sem credencial. Eles não medem
cota, cobrança nem qualidade de resposta. O projeto permanece um protótipo
local: `DEBUG`, CORS amplo e APIs sem autenticação estão configurados em
`desafio_itau/settings.py` e exigem revisão antes de expor uma chave paga.
