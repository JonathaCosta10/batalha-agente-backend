# Qualidade factual e tempo da conversa — 2026-09-27

## Pergunta testada

> Qual é o fluxo do cliente 1 da conversa até “E agora?”?

Na **demo Django**, as rotas `/api/v1/cliente/1/`, `/api/v1/chat/variavel-1/1/`
e `/api/v1/comunicacao/e-agora/1/` produziram esta resposta curta:

> Alexandre vê a conversa em modo NEUTRO (`TEXTO_1[NEUTRO]`). Ao tocar em
> “E agora?”, o Template 3 apresenta 5 produtos; nenhum aparece como Pré-Aprovado.

O [registro medido](medicoes/2026-09-27/cliente_1.json) contém fonte, horário BRT,
tempo total e tempo de cada rota. Uma execução local com o Django test client
durou **213,02 ms**. É uma medição única, no processo local, sem rede, navegador
ou LLM; não é latência de produção nem percentil. O comando reproduz a medição:

```powershell
..\.venv\Scripts\python.exe docs/qualidade-conversa/medir_cliente_demo.py 1
```

O módulo `apps/context_agent_datadriven/services/qualidade_fluxo.py` verifica
o mesmo ID e nome nas três respostas, tag compatível com chave/gênero, texto
ativo, botão, Template 3, score interno consistente e elegibilidade de cada
produto segundo seu mínimo. O teste negativo troca ID, tag e elegibilidade e
exige reprovação. O resultado `COMPROVADO_NA_DEMO` cobre **esses fatos**; não
avalia naturalidade, segurança financeira ou fidelidade de uma resposta LLM.

## Base transacional i.agora: ID diferente

A tabela `batalha-time-02-lxof.hackathon_dados.extrato_sintetico` usa UUID no
campo `id_usuario`. O valor literal `"1"` retornou **nenhum movimento** na
[medição do BigQuery](../estudo-i-agora/medicoes/2026-09-27/usuario_1_literal.json):
`VAZIO`, 2.687 ms totais e `data_base: null`. As somas ficaram `null`, pois
não há fatos para calcular. A tabela contém dados **sintéticos** do hackathon.
Não existe mapeamento comprovado entre `cliente_id=1` da demo e algum UUID
desse extrato.

A [consulta dirigida](../estudo-i-agora/sql/q07_fluxo_usuario.sql) recebe um
UUID e data de corte como parâmetros, filtra um único usuário e devolve apenas
totais por mês e até cinco categorias de saída. Não envia descrições de
transações nem dados de outros usuários. O
[medidor](../estudo-i-agora/sql/medir_usuario.py) impõe limite de 100 MB,
registra `job_id`, bytes, tempo e verificações aritméticas. Exemplo com UUID
autorizado:

```powershell
..\.venv\Scripts\python.exe docs/estudo-i-agora/sql/medir_usuario.py '<UUID>'
```

## Lacunas do agente atual

`enviar-mensagem` não recupera os fatos dessas rotas nem da tabela BigQuery.
Seu prompt recebe contexto do corpo HTTP e uma contagem de fontes da tese.
O `eval_harness` agora devolve `groundedness_score: null`, `eval_status:
NAO_MEDIDO` e `temporal_validation: NAO_MEDIDO` quando não há evidências
comparadas. O filtro mecânico de vazamento é separado. As views de conversa
devolvem `tempo_resposta_ms`, mas `sla_latencia_max_ms` continua sendo apenas
configuração. O cliente Google espera até 12 segundos por tentativa e pode
tentar dois modelos. **Qualidade factual e latência de uma resposta real do
LLM continuam NAO_MEDIDAS** aqui; a chave Google não está configurada.

Para responder sobre a base i.agora com o agente, falta um UUID autorizado,
recuperação dos fatos antes do prompt e validação das afirmações devolvidas.
Um ID inteiro da demo não deve ser convertido silenciosamente em UUID.
