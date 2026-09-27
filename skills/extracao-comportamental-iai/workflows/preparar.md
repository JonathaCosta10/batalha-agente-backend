# iai.preparar

1. PLAN: requer `google-cloud-bigquery` e ADC com leitura na tabela; sem chave de API. Caminho de evidência ÚNICO por clique.
2. GENERATE (da raiz do backend, venv em `backend/.venv`):
   `.venv\Scripts\python.exe skills/extracao-comportamental-iai/scripts/preparar_extracao.py --evidencia skills/extracao-comportamental-iai/evidencias/<clique>.json`
3. CRITIQUE: a evidência tem horário, fonte, corte, número do sorteio, UUID, linha, hash, `job_id`, bytes e duração?
   O número do sorteio é a posição na lista ordenada, não o ID do cliente da demo nem identificador estável.
4. REPAIR: falha de preparo grava `NAO_MEDIDO` com o motivo; não invente linha nem valor. Consultas sem cache.
5. VERIFY: a proposta esperada impressa vai para a chamada do agente; a carga do LLM continua só o texto do
   usuário (contrato `primeira-chamada`); os dados da extração ficam na etapa posterior do IAI.
