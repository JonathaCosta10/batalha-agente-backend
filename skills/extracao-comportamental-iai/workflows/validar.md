# iai.validar

1. PLAN: evidência em `AGUARDANDO_RESPOSTA` e proposta do agente em JSON estrito.
2. GENERATE: pré-guard offline
   `node skills/extracao-comportamental-iai/tools/gate.mjs --proposta <p.json> --evidencia <e.json>`;
   depois o guard real, que relê o BigQuery:
   `.venv\Scripts\python.exe skills/extracao-comportamental-iai/scripts/validar_resposta.py --evidencia <e.json> --proposta <p.json>`
3. CRITIQUE: o guard relê a lista de UUIDs (posição sorteada) e o extrato do UUID; compara tipo e valor de cada chave.
4. REPAIR: `REPROVADO` = proposta errada, devolva ao agente; `NAO_MEDIDO` = leitura falhou, diga que não mediu.
5. VERIFY: só em APROVADO sai `{aprovado, id_extracao, numero_usuario, id_usuario, resposta}` (templates/resposta-liberada.md).
