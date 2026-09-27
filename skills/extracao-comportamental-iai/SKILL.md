---
name: extracao-comportamental-iai
description: Sortear um usuário UUID e um movimento do extrato BigQuery i.agora no clique IAI, gravar evidência e reprovar a proposta do agente que diverge da fonte ou do contrato de resposta.
triggers: [clique IAI, sortear usuario UUID, extrato sintetico BigQuery, proposta do agente IAI, guard de extracao, validar resposta IAI, evidencia de extracao]
allowed-tools: [Read, Bash]
state: candidata
version: 0.2.0
owner: repo
escopo: local
---

# Extração comportamental IAI

Este kernel só roteia. Leia `manifest.yaml` e `routes/router.yaml`; o router escolhe UMA rota; carregue só o
que ela lista em `loads` e siga o workflow dela (PLAN, GENERATE, CRITIQUE, REPAIR, VERIFY).

Fonte: tabela **sintética** `batalha-time-02-lxof.hackathon_dados.extrato_sintetico`, usuários em UUID. O
número `1..1000` do app demo NÃO identifica ninguém nessa tabela. O contrato único é
[contrato-de-extracao-e-resposta.json](contrato-de-extracao-e-resposta.json), lido pelos scripts e pelo pré-guard.

Faz:

- sorteia a posição `1..N` na lista ordenada de UUIDs (`secrets.randbelow`) e uma linha existente do extrato;
  grava evidência com fonte, corte, hash, `job_id`, bytes e duração (`scripts/preparar_extracao.py`);
- relê o BigQuery e compara linha, campo e valor com a evidência (`scripts/validar_resposta.py`); só o texto
  montado pelo guard é publicado, nunca texto livre do agente;
- pré-guard offline, sem BigQuery, da forma da proposta (`tools/gate.mjs`), com casos golden e adversariais.

Não faz, de propósito:

- ligar o botão IAI no front ou no Django: os scripts ainda não são chamados por nenhum dos dois;
- associar o UUID ao cliente inteiro da interface sem tabela de correspondência comprovada;
- medir qualidade semântica de texto livre nem provar que a base sintética representa pessoa real.

Invariantes:

1. Planilha limpa: valores preservados; nulo ou tipo inesperado em campo obrigatório é recusa.
2. Proposta com chave a mais, tipo trocado ou fato diferente sai `REPROVADO`; falha de leitura sai `NAO_MEDIDO`.
3. Evidências ficam em `evidencias/` (ignorado pelo Git); não envie esse JSON ao usuário.
4. `node tools/gate.mjs` tem de acabar em `TUDO OK` antes de a skill mudar de estado.
