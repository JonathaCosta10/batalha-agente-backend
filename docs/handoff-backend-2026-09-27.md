# Handoff do backend — 2026-09-27 (sessão d9, que fecha o backend)

Por ordem do dono (10:18 BRT), o backend fecha numa sessão só, esta. A f7 manda a parte dela (hash, P0/P1) para entrar aqui.

## Commits
| Repo | Branch | Hash | Estado |
|---|---|---|---|
| desafio-itau-batalha-de-agentes-time2 (clone publicado, D-7) | feat/decisoes-d3-d7-deploy-2026-09-27 | cb9d8c8 | **pushado** 10:17 (autorizado pelo dono) |
| agente-app-mobile | docs/entrega-consolidada-2026-09-27 = origin/main | 706565c (sorteio por id_usuario) | pushado pela d2 em 569e051 |
| agente-app-mobile | docs/entrega-consolidada-2026-09-27 | e4db09c (nome vindo do id) + de8c631 (handoff d2) | **pushado** às 10:24 BRT em origin/main e na branch (fast-forward; autorizado pelo dono) |
| desafio-itau-time2 (f7) | feat/politica-versionada-estados-2026-09-27 | e8e5494 (fast-forward sobre o cb9d8c8; 18 arquivos) | **pushado** 10:32 pela f7 (autorizado 10:16); f7 encerrada |
| backend-agente-conversacional | — (sem git) | — | pasta local; o código vivo está no clone cb9d8c8 |

## Identidade do cliente (agent_backend)
- O servidor sorteia um `id_usuario` real do BigQuery (catálogo DISTINCT com cache de 15 min, dry-run com teto de 100 MB) e o grava na sessão antes do load (`planning/http.py`, `store.picks`).
- "Tentar de novo" mantém a pessoa. Só `sessao/abertura` com `next:true` sorteia outra, sempre diferente da atual. `DELETE plano/` mantém a pessoa.
- **Nome** (dono, 10:22 BRT): vem de `planning/nomes_por_id.json`, gerado a partir de `data/usuarios_verdade.csv`. O sha256 do CSV é conferido com o selo e a semente é `organizesee-usuarios-verdade-v1`. É um nome **gerado**, não é dado do cliente, e `person.nomeSelo.natureza = "nome_gerado"` diz isso. Um id fora do mapa recebe `null`, e o front mostra "Olá" neutro.
- **Gênero**: nunca é servido (`null`). O padrão é neutro, e o dono despriorizou o gênero às 10:17.
- Não existe mais "Pessoa N da base" nem rótulo "Cliente".
- `person.idUsuario` é a chave que mantém a sessão e a autenticação.
- Se a fonte falhar: 503 `{"erro":"perfil_indisponivel","motivo":…,"estado":"NAO_MEDIDO","codigo":"source"}`. O front (d2, 5f4fd75) mostra o motivo e o código.

## Relatório final da f7 (10:32)
- Verificação ponta a ponta com 3 ids reais: 27d41be5 e a77d3b65 (Livre) e 8a0df84f (Esbanjador); 11 meses; schema 1.1.
- P0 corrigidos pela f7: o convite 50/30/20 dava 503 vazio (o guard lia "mais equilibrada" como equilíbrio); o gênero ia para o cliente e para o prompt em conversas/.
- **P0 em perfil_usuario (d9), corrigido às 10:38 no código:**
  - o 201 de definir/ devolve só {codigo, pessoa, nome_origem};
  - o prompt ficou neutro, com "você";
  - índice posicional agora dá 400.
  - Os testes estão sendo migrados para UUID; resultado na seção de suítes.
- P0 de integração, fora deste repo: `frontend-agent-conversacional/src/services/planApi.ts:34` manda `ref: person.id + 1` (índice) para i-agora/plano/proposta. Tem de mandar `person.idUsuario`. Dono: sessão front (f1).
- NAO_MEDIDO:
  - conversas/mensagens/ com o contrato certo;
  - comunicacao-v1.json não é lido em execução (o tom vem de t3.PERFIS_DE_RESPOSTA);
  - Gemini não foi chamado (demo);
  - no auditor faltam o molde "R$ 200 → R$ 1.200" e o caso 75.
- No clone limpo, sem banco migrado: 29F/27E ("no such table sessaoperfilusuario"), com ou sem o commit da f7. Falta migrar no Dockerfile/entrada, ou documentar.
- Sem commit, fora do push: a correção do bloco de decisões em agente-app-mobile/docs/artefatos/paginas/batalha-agentes-unificado.html.
- Artefato da f7: https://claude.ai/artifact/T3khuMUVtF2Q2WhA6SBL2P

## Suítes (relógio BRT, 27/09)
- agent_backend: 105 passam e 3 falham às 10:26. As 3 falhas já existiam: `test_gcs_survives_new_instance…`, `test_persistent_budget_survives_runtime_reset` e `test_prompts` (encoding).
- backend-agente-conversacional: 517 OK com 21 xfail às 09:57 (origem) e às 10:02 (clone).

## Bloqueados (de quem, e o que se espera)
1. **Cloud Run**: o Henrique precisa responder ao OK do serviço novo `i-agora-conversacional`, à SECRET_KEY e ao IAM do BigQuery. Comando em `docs/decisoes-e-logica-2026-09-27.md` §5.4, NÃO EXECUTADO.
2. **Custo em bytes do catálogo no ar**: NAO_MEDIDO. A estimativa é de ~21,5 MB por atualização, pela lista de 05:26.

## Protótipo funcional: estado às 10:43 BRT e limitações declaradas
- **Backend local no ar:** `runserver 127.0.0.1:8000`, a partir desta pasta. O `/healthz` dá 200. O proxy do front (:3000 → :8000) deixou de dar 502.
- **Identidade:**
  - O id_usuario é real, vindo do BigQuery.
  - O nome mostrado é **gerado** por semente para esse id (`nome_origem: "nome_gerado"`), não é o nome real do cliente.
  - O gênero é **sempre neutro**: não sai na API e não entra no prompt; o tratamento é "você".
- **Suíte desta pasta às 10:42:** 545 testes OK, com 22 falhas esperadas. As falhas documentam divergências da especificação e uma rota de conversas que ainda expõe gênero no bootstrap (`apps/conversas`, xfail).
- **Limitações declaradas:**
  1. O Cloud Run **não foi publicado.**
     - O segredo `i-agora-conversacional-django` foi criado às 10:41 e a conta de serviço tem acesso a ele.
     - O build e o deploy foram recusados pelo controle de permissões desta sessão. O dono roda o comando da §5.4 com `!`.
  2. As correções de `perfil_usuario` (definir/ e pergunta/ neutros, índice → 400) estão **só nesta pasta**, que não tem git. O `e8e5494` pushado ainda não as tem.
  3. O GET de bootstrap de `apps/conversas` ainda devolve gênero e índice (xfail). Nenhum front mostra esses campos.
  4. As rotas `usuario-real/<ref>/` e `i-agora/plano/proposta/` ainda aceitam índice posicional.
  5. A sessão vive no SQLite local. No Cloud Run seria efêmera, com uma instância só.
  6. O Gemini roda em modo demo. O custo em bytes do catálogo no ar é NAO_MEDIDO.
  7. A base é **sintética** (extrato_sintetico).

## Onde está a lógica
- Decisões D-1 a D-19: `docs/decisoes-e-logica-2026-09-27.md`
- Backlog: `docs/backlog.md`
- Mapa: https://claude.ai/artifact/Su18p6bHUYKcGKgfSvd4Qz (v13)
- Front: `agente-app-mobile/docs/handoff/2026-09-27-front-sessao-d2.md`
