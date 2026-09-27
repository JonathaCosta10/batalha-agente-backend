# iai.verificar

1. PLAN: depois de mudar o contrato, `scripts/*.py`, `tools/gate.mjs` ou os evals.
2. GENERATE: `node skills/extracao-comportamental-iai/tools/gate.mjs` — evals offline e depois
   `scripts/testar_skill.py` com `$PYTHON` (ou `.venv` da raiz do backend). Sem Python, a parte unittest sai
   `NAO_MEDIDO` e o código de saída é 2, nunca OK.
3. CRITIQUE: cada caso em `evals/adversarial/` TEM de reprovar (prova negativa); um que passa bloqueia a mudança.
4. REPAIR: corrija o pré-guard ou o contrato, nunca o caso adversarial para o fazer passar.
5. VERIFY: cite a linha `TUDO OK — N/N casos, A/A provas negativas apanhadas` e a contagem do unittest.
