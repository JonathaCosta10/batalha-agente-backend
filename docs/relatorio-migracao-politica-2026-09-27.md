# Relatório — migração de regras para política versionada e fluxo controlado (2026-09-27)

Protótipo local. Nada foi publicado nem enviado a clientes, e não houve deploy nem commit. O protótipo não é canal oficial do Itaú.

## 1. Arquivos lidos e escopo

**Código e configuração lidos:**
- `README.md` e `desafio_itau/modelos_llm.py`
- `apps/conversas/`:
  - `gateway.py`, `rules.py`, `schemas.py`, `views.py`, `service.py`, `context.py`, `projection.py`
  - `interacao*.py`, `extremos.py`, `fairness.py`
  - os prompts `.liquid` e o `renderer.py`
- `apps/conversas/knowledge/*.json` (a RC 8 e a RC 20/2026)
- `…/i_agora/t3.py` e `guard.py`
- `agentes/LLM_Models/google/cliente.py`
- `tests/conversas_apoio.py`

**Varredura dos MDs:** um subagente inventariou os MDs de regras e os catálogos de produto; os achados estão no §6.

**Modelo:**
- **Configurado:** `gemini-3.5-flash-lite` (primeira chamada e contingência) e `gemini-flash-latest`.
- **Evidência real:** o ledger `relatorios/avaliacoes/2026-09-27.jsonl` tem `modelVersion` `gemini-3.5-flash-lite` em 34 tentativas e `gemini-flash-latest` → 429 em 19.
- **Divergência registrada:** o pedido fala em "Gemini 3.8", mas nenhuma chamada a 3.8 existe no código. O modelo **não foi trocado**. O registro está em `modelos_llm.INTEGRACAO`.

## 2. O que saiu de MD/código espalhado e para onde

Tipos de conteúdo: fato, regra institucional, regra operacional, comunicação, exemplo, hipótese.

| Conteúdo | Classe | Destino | Por quê |
|---|---|---|---|
| Limiares 1% (equilíbrio), 10% ou ≥ 1 multa (dívida), 15% (T3), inclinação 3 m / 15-30-50, 50/30/20, hipóteses 5%/8% | regra operacional | `desafio_itau/politica/operacional-v1.json` (rule_id, versão, condição tipada, origem, testes; aprovação PENDENTE) | Estavam como literais em 4 arquivos. Agora têm uma fonte com sha256 e a referência vai no contrato |
| Avaliação das condições | função | `desafio_itau/politica/__init__.py` (`operator`, lógica de Kleene, sem `eval`) | Um indicador ausente vira NAO_MEDIDO, nunca zero |
| Termos proibidos (garantia, pré-aprovado, julgamento, urgência) | comunicação / controle | `politica/lexico-v1.json` + `lexico.py` | O regex fixo não tratava negação, citação nem Unicode |
| Erros de API 400/404/429/503/504 | regra operacional | `politica/erros_api-v1.json` + `erros_api.py` | Pedido do dono no meio da tarefa |
| Perfis, bordão, frases fixas | comunicação | `politica/comunicacao-v1.json` | Sem manual de marca, o bordão fica NAO_APROVADO |
| Estados da conversa e contrato público | função + schema | `apps/conversas/estado.py`, `schemas.ContratoRespostaV1` | A transição passa a ser explícita e auditável |
| Texto da RC 8 | fato normativo | já estava em JSON; agora conferido com a API do BCB | ver `docs/rc8-rastreabilidade-2026-09-27.md` |

Nenhum original foi apagado. Os módulos antigos passam a ler a política, e o valor calculado ficou igual ao anterior (teste de equivalência com oráculo independente).

## 3. Fluxo implementado e controles propostos

**Implementado:**
- **Pipeline:** extremos → input_guard → contexto → rascunho → checagens determinísticas, que incluem o `estado.decidir()` e a regra de que **número sem fonte reprova antes do output_guard** → output_guard → `release()` com o `contrato` já decidido e o `erro_api`. (Corrigido 2026-09-27 09:37: a versão anterior punha o `estado.decidir()` depois do output_guard; a ordem do código está em `service.py`, `_pipeline`.)
- **Invariantes do `estado.decidir()`:**
  - Uma afirmação financeira sobre fato do extrato exige dados MEDIDO; sem isso, levanta `TransicaoInvalida`.
  - `INDISPONIVEL` não tem nenhuma ação permitida.
- **Dinheiro:** `Decimal`, com a comparação feita antes do arredondamento.
- **Correção:** no máximo uma nova chamada ao modelo alternativo, depois fallback seguro.

**Proposto e não implementado:**
- rota de handoff humano (NAO_IMPLEMENTADO);
- checagem de meses faltantes;
- deduplicação fatura × compras de cartão;
- separação de transferência própria;
- catálogo de produtos aprovado.

## 4. Testes executados

`../frontend-agent-conversacional/.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"` (na raiz do repo)

| Momento | Resultado |
|---|---|
| Linha de base | 254 OK |
| Fim da 1ª rodada | 311 OK + 1 falha esperada (2026-09-27 ~09:00 BRT, 13,9 s) |
| Fim da 2ª rodada | **365 OK + 3 falhas esperadas** (2026-09-27 ~09:20 BRT, 12,6 s; inclui os arquivos novos da sessão d9) |

**A falha esperada** é uma limitação conhecida do léxico: uma paráfrase de promessa sem as palavras do catálogo passa.

**Arquivos novos:**
- `test_politica_operacional.py`: equivalência, provas negativas de schema, guard AST sem eval (com prova negativa) e as fronteiras:
  - 10,00% exato é relevante;
  - 9,96% não é;
  - a multa sozinha basta;
  - nulo vira NAO_MEDIDO;
  - 1% é limite estrito.
- `test_lexico_e_erros_api.py`: negação, citação, variantes Unicode, a tabela de erros, a nova chamada no gateway (máx. 1; nenhuma para 401/500) e o envelope do serviço.
- `test_estado_contrato.py`: roteamento por estado e invariância (paráfrase, troca de valor, troca de titular).
- `test_comunicacao_e_corpus.py`: deriva do bordão e das frases fixas contra a origem literal, integridade do corpus e o runner em modo NÃO EXECUTADO.

**Avaliação da LLM:**
- Corpus de 30 casos × 5 repetições em `tests/avaliacao/corpus-llm-v1.json`, com runner `scripts/avaliar_llm.py --real`.
- **NÃO EXECUTADO.** Gastaria até 450 chamadas, e a cota gratuita medida do 3.8 é de 20 por dia.
- Mocks não provam o comportamento do Gemini.

## 5. Exemplos rastreáveis (dos testes, dados sintéticos)

- **Aceito:**
  - Rascunho: "Pelo extrato, as saídas médias foram de R$ 10.790,43 por mês." com claim `outflows`.
  - Resultado: 200, `contrato.estado = ANALISE_DESCRITIVA`, `evidence_ids = ["outflows"]`, período preenchido.
- **Bloqueado:**
  - Rascunho: "Suas saídas foram de R$ 9.999,99 por mês." sem claim.
  - Resultado: 503, `INDISPONIVEL`, sem chegar ao output_guard; o número não aparece na resposta.
- **Fallback por provedor:**
  - O Gemini responde 429 duas vezes: a do modelo primário e a da nova chamada ao alternativo.
  - Resultado: 503, `erro_api = {codigo: 429, origem: "provedor", acao_cliente: "aguardar_e_tentar_novamente", tentar_novamente_em_s: 30}`.
- **Encaminhamento:**
  - Entrada: "quero me matar".
  - Resultado: `ENCAMINHAMENTO` com resposta fixa e **zero** chamadas ao modelo.

## 6. Limitações

**Dados e aprovação:**
- Os dados são sintéticos.
- Nenhuma regra tem aprovação institucional: todas estão PENDENTE.
- Não existe manual de marca.

**Dados financeiros (achados do inventário):**
- Mês faltante sai da média e a infla.
- A fatura é somada junto das compras do cartão, com risco de contagem dupla (NAO_VERIFICADO).
- "Recebimentos diversos" pode conter transferência própria.
- Há 4 catálogos de produto com taxas sem fonte, entre eles "112% CDI". O chat não os usa e bloqueia menção a produto.
- Os cortes de score divergem (750/450 contra 650).
- O `consultas.py` duplica o limiar de 15%.

**Temperatura:**
- `conversas/` não envia temperatura, o que coincide com o 1.0 do guia Gemini 3, atualizado em 2026-09-23.
- As rotas legadas usam 0,35, 0,4 e 0,30. Só estão registradas; não foram alteradas.

**Léxico:** uma paráfrase fora do catálogo passa (a falha esperada do §4). O output_guard feito pelo modelo continua sendo a segunda linha.

**Frases fixas:**
- As divergências de texto estão no §7.
- `FORA_DO_CONTEXTO` é PROVISORIO.

## 7. Próximos passos, por risco

1. **Alto:**
   - checagem de meses faltantes;
   - dedup fatura × cartão;
   - transferência própria fora da renda. Os três alteram números mostrados ao cliente.
2. **Alto:** rodar `avaliar_llm.py --real` com cota paga ou em vários dias, mais a rubrica humana.
3. **Médio:** aprovação institucional de `operacional-v1.json` e `comunicacao-v1.json`, com dono nomeado na matriz RC 8.
4. **Médio:** alinhar a temperatura das rotas legadas e decidir o modelo (3.5-flash-lite contra 3.8).
5. **Baixo:**
   - unificar os cortes de score e o 15% do `consultas.py`;
   - resolver o texto divergente de `extremos.PROVISORIO`: o roteiro diz "sou uma máquina", o código diz "assistente virtual".

## 7-A. Situação das pendências (2ª rodada, 2026-09-27 09:05–09:24 BRT (relógio medido; cartões anteriores diziam 09:45 por estimativa))

**Suíte:** 365 OK + 3 falhas esperadas. As 3 são: a paráfrase do léxico, deste relatório, e duas dos arquivos novos da sessão d9. Os achados D2–D11 são da sessão d9 (`docs/rota-integrada-batalha-agentes-backend.md`).

### COMPLETA (código + teste com prova negativa + documento)

| Item | O que mudou | Prova |
|---|---|---|
| Aviso NAO_MEDIDO reprovado (bug d9) | `guard_situacao` aceita só a abstenção explícita ("não vou afirmar se…"); "não sobrou" continua reprovado | `test_guard_situacao_abstencao.py` |
| D2: rótulo T3 no texto | léxico 1.1.0 `rotulo.segmento_interno` (Vulnerável/Esbanjador/segmento Livre/perfil_t3), sem exceção para negação ou citação; vale em `mensagens/` (safe_text) e `interacao/` (`politica.rotulo`). Varredura de 1.896 frases fixas: nenhum acerto em texto ao cliente (só em `.alerta`/`regras`, que são metadados) | `test_pendencias_fechadas.RotuloT3NoTexto` |
| D3: ttl da conversa | 30 min → 4 h, igual à sessão | `test_ttl_da_conversa_igual_ao_da_sessao_d3` |
| D5: nomes no documento | §5.4 corrigida para os campos reais de `ContratoRespostaV1` | — |
| D6: 401/403/405/409 | `erros_api` 1.1.0 com linhas só de API | `test_codigos_so_da_api_d6` |
| D7: origem do erro | status desconhecido ou do provedor → `NAO_CLASSIFICADO` com o código real e a origem verdadeira | `test_provedor_fora_da_tabela…`, `test_falha_do_provedor_sem_status…` |
| D11: 429 global | bloqueio por usuário | `test_bloqueio_por_usuario_nao_global_d11` |
| 15% duplicado | `consultas.LIMIAR_SOBRA_SAUDAVEL_PCT` lido de `t3.limiar_surplus` | `LimiarUnico` |
| Status do catálogo de produtos | `politica/produtos-v1.json`: `SEM_CATALOGO_APROVADO`; ausência = NAO_MEDIDO, nunca custo zero; 4 fontes sem taxa listadas | `CatalogoDeProdutos` |
| I2: ordem dos modelos (3ª rodada, 09:35) | `MODELOS_GOOGLE` = [gemini-3.5-flash-lite, gemini-flash-latest]. Evidência: ledger `relatorios/avaliacoes/2026-09-27.jsonl`, com gemini-flash-latest em 429 em 19 de 19 tentativas e gemini-3.5-flash-lite com 32 aprovadas, 2 reprovadas pelos guards e 1 em 429. O input_guard de `interacao/` usa o modelo com cota (`_modelo_do_guard`). Nenhum modelo trocado. As rotas legadas (`rotas_base.yaml`, `manager.py`) seguem com flash-latest literal | `OrdemDosModelos` (com prova negativa) |
| Deriva da comunicação, corpus/runner, matriz RC 8, §5.4 | ver §4 e `docs/rc8-rastreabilidade-2026-09-27.md` | `test_comunicacao_e_corpus.py` |

### PARCIAL (entregue o que dá para provar; evolução futura descrita)

| Item | Entregue | Falta (evolução) | Depende de |
|---|---|---|---|
| Meses faltantes na média | `meses_faltantes()`; `media.cobertura` = COMPLETA/LACUNA e `meses_faltantes` também em `situacao_conversa`. Os números **não** foram alterados | 1) política de tratamento (pedir dado, excluir ou imputar); 2) detectar lacuna nas pontas da janela, o que exige a janela esperada vinda do SQL; 3) guard que impeça afirmar média com LACUNA sem ressalva | dono (regra) |
| Detector de extremos | recall no corpus da d9: **3/12 → 7/12** (medido 2026-09-27 ~09:15, `scripts/gemini_trabalho_pesado.medir`). Ideação indireta inequívoca, flerte abreviado, "odeio você". Prova negativa: "sumir com a dívida", "odeio esse banco", "não aguento mais essa fatura" não disparam | 5 frases ambíguas ("cansado de lutar sozinho", "pressão na cabeça", "voz irritante", "queria que fosse de verdade", "robô simpática") exigem decisão clínica, porque exibir o CVV para desabafo é escolha de produto. Recall em 60 frases não é garantia de produção | dono + taxonomia F3 |
| Controle do harness (item 3 do front) | `GET conversas/status/` (§5.5): modelo configurado × `modelVersion` observado, orçamento do processo, limites, últimas 20 chamadas sem texto | orçamento **diário** (NAO_IMPLEMENTADO); cota restante do provedor não é observável (NAO_MEDIDO); métricas só em memória | — |
| Avaliação da LLM 30×5 | corpus, métricas com denominador e runner (`--real`) | **NÃO EXECUTADO**: até 450 chamadas, e a cota compartilhada com o time é de 20/dia no 3.8 | dono (cota/custo) |
| Léxico por paráfrase | catálogo contextual + output_guard do modelo | classificador semântico; hoje é a falha esperada documentada | — |
| Encaminhamento humano | `erro_api.encaminhar_humano` e estado `ENCAMINHAMENTO` sinalizam | rota de handoff real: NAO_IMPLEMENTADO | canal de atendimento |

### NÃO FEITO: depende de dado, de terceiro ou de decisão fora da engenharia

| Item | Por que não | Próximo passo |
|---|---|---|
| Fatura × compras de cartão (contagem dupla) | exige vínculo fatura↔compras no BigQuery; hoje NAO_VERIFICADO | medir no extrato quais lançamentos de fatura têm compras correspondentes |
| Transferência própria como renda | o dado não identifica contas do mesmo titular | campo de contraparte ou lista de contas do titular |
| Aprovação institucional (política, comunicação, bordão, frases PROVISORIO, texto de extremos) | não é decisão de engenharia | dono nomeado na matriz RC 8 |
| Temperatura das rotas legadas; 3.5-flash-lite × 3.8 | trocar muda comportamento; o pedido proíbe troca silenciosa | decisão do dono, com avaliação 30×5 antes e depois |
| ~~D9: `schema_version` 1.1 × 1.0 em `interacao/`~~ | resolvido na 3ª rodada (abaixo), com aprovação do dono às 09:41 | — |
| Dezembro completo (publicado) × média jan–nov (esta base) | a regra do dono (06:22) vale aqui; o publicado está em outro repositório | reconciliar no `agente-app-mobile` |
| Cookie de 30 dias; `/api/health/` com nome fixo | estão no backend publicado, não neste repositório | aplicar lá o equivalente das §5.4–5.5 |
| Levar as rotas para git (item 4) | decisão do dono (I7); push só com autorização explícita | — |
| Cortes de score 750/450 × 650 | sem fonte que diga qual vale | dono escolhe e registra em `operacional-v1.json` |

### 3ª rodada (2026-09-27 09:42–09:55 BRT, relógio medido): I4, I5 e D9, aprovados pelo dono às 09:41

| Item | Situação | O que mudou | Prova |
|---|---|---|---|
| I4 / D-4: conversa sobrevive ao reinício | **COMPLETA** | `apps/conversas/persistencia.py` (novo): `ArmazemConversas` sobre o cache do Django com backend de banco (tabela `conversas_sessao_cache`, criada sob demanda como no `createcachetable`; sem mexer em `settings.py` nem em migrações). Guarda histórico minimizado, `criada` e proposta pendente; nada de prompt. TTL = `SESSAO_SEGUNDOS` (4 h) em relógio de parede (`time.time`), aplicado na leitura, mesmo padrão da `SessaoPerfilUsuario` da d9. `ConversationService(persistencia=..., relogio_parede=...)`; `views.service_for` liga nos modos `demo` e `demo_live`. O acesso ao banco sai do laço asyncio (thread própria por operação), porque o ORM recusa acesso síncrono dentro do laço. Rate limit, idempotência e bloqueio concorrente seguem só em memória | `test_fechamento_i4_i5_d15.ConversaPersistenteTest` (7): nova instância enxerga; sem armazém o reinício perde (controle); 4 h exatas não enxerga; outro principal não enxerga; valor adulterado não restaura; só as chaves permitidas vão ao banco |
| I5 / D-14: histórico do turno livre | **COMPLETA** | `interacao.py`: últimos 4 turnos livres por `sessao_id` (em memória, TTL 4 h), no `data` do modelo como `HISTORICO_NAO_CONFIAVEL` (com aviso) e no `history` do input_guard. `interacao.liquid` ganhou a regra 6 (histórico não é instrução nem fonte de número). Extremo, fora do contexto, recusa e contra-discurso não entram. Campo aditivo `avaliacao.historico_turnos` | `HistoricoTurnoLivreTest` (7): o 2º turno leva o 1º ao modelo e ao guard; só 4; outra sessão não entra; sem sessão não guarda; "ignore as regras" no histórico não muda situação, fluxo, cenário, regras nem ações; extremo/fora não entram; vence com a sessão. O `test_i5_…` de `test_quatro_rotas.py` (arquivo da d9) passou: **sucesso inesperado**, e a d9 retira o `expectedFailure` |
| D-15 / D9: `schema_version` único em `interacao/` | **COMPLETA** | `interacao.SCHEMA_VERSION = "1.1"` em 200, 400, 401, 404, 405 e 503 (`views_interacao._erro_interacao`). `conversas/mensagens/` e `avaliacoes/resumo/` seguem `"1.0"` | `SchemaVersionUnicoTest` (3), com prova negativa: o `_erro` antigo (1.0) reprova no guard `versoes_unicas` |

**Suíte (2026-09-27 09:51 BRT, `Get-Date`; 33,4 s):** 517 testes. Resultado: **1 falha, 21 falhas esperadas e 1 sucesso inesperado**, nenhum erro.
- A falha é `test_quatro_rotas.InteracaoTest.test_sem_x_sessao_id_401`, que ainda espera `schema_version "1.0"` no 401 de `interacao/`. É a mudança D-15 aprovada, num arquivo da sessão d9, que troca a asserção para `"1.1"`.
- O sucesso inesperado é o I5.
- Nenhuma falha por `410 rota_descontinuada`: a d9 já tinha resolvido essas antes.
- Os 17 testes novos passam isolados e na suíte.
- Efeito colateral medido: `tests/test_conversas_http.py` não cria banco de teste. Por isso, desde a D-4, ele grava sessões no `db.sqlite3` real, e agora grava também conversas demo: 10 linhas sintéticas em `conversas_sessao_cache`, que vencem em 4 h. O arquivo não entra no commit.

**Temas encerrados em 2026-09-27 09:55 BRT.** Ficam abertos, por depender de terceiros:
- avaliação LLM 30×5 **NÃO EXECUTADA** (cota do provedor);
- aprovação institucional da política, da comunicação e dos textos de extremos **PENDENTE** (dono nomeado);
- fatura × compras de cartão e transferência própria como renda **NÃO FEITO** (dado);
- rota de handoff humano **NAO_IMPLEMENTADO** (canal de atendimento);
- orçamento diário e cota restante do provedor **NAO_MEDIDO**;
- cortes de score 750/450 × 650 (dono);
- reconciliação dezembro × média jan–nov e cookie de 30 dias no backend publicado (outro repositório);
- as 2 linhas de `test_quatro_rotas.py` acima (d9).

### Verificação ponta a ponta por id_usuario (10:13–10:28 BRT, relógio medido)

Três id_usuario reais sorteados no BigQuery (`ORDER BY FARM_FINGERPRINT(...) LIMIT 3`, job `fc1b359d-2c2b-43d6-8dfc-7b0e8ff051e5`, 17.768.230 bytes, 10:13:54 BRT). Cada um passou por `perfil-usuario/definir/` e depois por `conversas/interacao/` (`bot.intro`, `bot.convite_50_30_20`, `livre.respostas`), com Django test client, `CONVERSAS_MODO=demo` e sem Gemini.

| id_usuario | meses / faltantes / cobertura | T3 (taxa de sobra; inflow / outflow mensal) | tom (t3.PERFIS_DE_RESPOSTA) | situação / fluxo |
|---|---|---|---|---|
| 27d41be5… | 11 / [] / COMPLETA | Livre (19,86 %; 10.885,42 / 8.723,90) | consultivo | SOBROU / LIV-SOBROU |
| 8a0df84f… | 11 / [] / COMPLETA | Esbanjador (2,6 %; 10.874,84 / 10.592,55) | direto e encorajador | SOBROU / ESB-SOBROU |
| a77d3b65… | 11 / [] / COMPLETA | Livre (22,76 %; 11.389,63 / 8.797,84) | consultivo | SOBROU / LIV-SOBROU |

Fonte das linhas: `usuario_real.perfil`, com jobs próprios por id (selo `cache: false`). O `schema_version` foi `1.1` em todas as respostas.

**Achados e correções** (testes em `tests/test_identidade_por_id_usuario.py`, 8 testes com prova negativa):
- **P0, 3 de 3 ids.** `bot.convite_50_30_20` devolvia 503 com `texto`, `erro`, `mensagem` e `erro_api` todos null. A causa era o guard de situação: ele lia "vida financeira *mais equilibrada*" como se o texto afirmasse EQUILIBRIO. Correção em `interacao_avaliacao.PISTAS`, que agora exclui "mais equilibrad…". O 503 passou a levar `erro`, `mensagem` e o envelope `erro_api` com `acao_cliente`; o mesmo vale para 400, 401, 404 e 405 de `interacao/` (`views_interacao.py`). Reexecução às 10:28: 200 nos 3 ids.
- **P0: gênero servido.** Pela regra do dono das 10:22, o nome gerado do mesmo id vale e o gênero nunca vale. `dados.titular` levava o gênero e o índice posicional. O prompt de `interacao/` e o de `mensagens/` levavam o gênero, e `identity_draft` fazia concordância ("identificada"). Agora `dados.titular = {id_usuario, pessoa, nome_origem: "nome_gerado"}`. Os prompts e a identidade não dependem do gênero (prova: F e M dão o mesmo texto). O guard `nome.genero` reprova as duas formas de particípio. O card usa a frase sem gênero. O ledger grava `id_usuario_sha256_12` no lugar do índice.
- **Pendências d9** (`services/perfil_usuario.py`):
  - `:98-99` devolve `genero` e `indice` no 201 de `definir/`;
  - `:188-203` põe o gênero no prompt de `perfil-usuario/pergunta/`;
  - `:88-91` aceita índice posicional.
- **NAO_MEDIDO / fora do escopo:**
  - `conversas/mensagens/` respondeu 400 ao payload do script, e não se mediu a rota com o contrato correto;
  - `comunicacao-v1.json` não é lido em execução, porque o tom vem de `t3.PERFIS_DE_RESPOSTA`;
  - o front (`frontend-agent-conversacional/src/services/planApi.ts:34`) manda índice posicional e não chama `definir/`.

**Suíte (10:28 BRT):** 540 testes, OK, 21 falhas esperadas, 0 pulados.

## 8. Tese defensável

Com regras numéricas versionadas e avaliadas por código, com estado explícito e contrato público, e com número liberado só quando tem fonte, o protótipo torna **auditáveis e testáveis** as decisões que antes dependiam do texto do modelo: por que respondeu, com qual regra e com qual dado. Isso **não** garante texto determinístico, ausência universal de alucinação nem conformidade regulatória certificada. O que garante é que, nos casos cobertos pelos testes, a violação é detectada e contida antes de chegar ao cliente, e que o que não foi medido aparece como NAO_MEDIDO.
