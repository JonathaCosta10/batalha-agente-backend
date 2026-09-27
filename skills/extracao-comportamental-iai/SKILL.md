---
name: extracao-comportamental-iai
description: Sortear um usuário UUID e um fato de seu extrato BigQuery i.agora no clique IAI, registrar evidências e bloquear propostas do agente que não coincidam com a fonte ou o contrato de resposta.
---

# Extração comportamental IAI

Esta skill fornece a fronteira de dados do futuro clique IAI. A fonte é a tabela **sintética** `batalha-time-02-lxof.hackathon_dados.extrato_sintetico` no BigQuery, cujos usuários são UUIDs. O número inteiro `1..1000` do app demo não identifica um usuário nessa tabela. A integração do botão e a contextualização do agente pertencem à outra seção; os scripts daqui ainda não são chamados pelo front ou pelo Django.

O arquivo [contrato-de-extracao-e-resposta.json](contrato-de-extracao-e-resposta.json) define fonte, corte, campos sorteáveis, proposta e saída pública. `SKILL.md` e `scripts/` são nomes exigidos pela estrutura da skill; os nomes dos demais arquivos e as chaves do contrato estão em português.

## Decisões de dados

- A cada clique, obtenha os UUIDs existentes até a data de corte, ordene a lista e sorteie sua posição de `1..N` com `secrets.randbelow`. Essa posição é o **número do sorteio** mostrado na resposta; não é o ID inteiro do cliente da demo nem um identificador estável. Consulte somente o extrato do UUID naquela posição e sorteie uma linha existente. O valor sorteado é o `vlr` dessa linha; o comportamento registrado é o tipo do movimento e sua categoria original.
- Considere a planilha limpa: preserve os valores da tabela, sem normalizar categorias, texto ou valores monetários. Conversão de `TIMESTAMP` para ISO é apenas serialização JSON. Campos obrigatórios nulos ou tipos inesperados causam recusa.
- Não associe o UUID sorteado ao cliente inteiro da interface sem uma tabela de correspondência comprovada. Esta skill usa o UUID como identificador público da extração.
- A proposta do agente deve ser JSON estrito e conter somente os campos declarados. O guard relê o extrato do mesmo UUID e compara a linha, o campo e o valor com a evidência. O texto liberado é construído pelo guard; texto livre do agente não é publicado.
- O guard verifica a estrutura e os fatos selecionados. Ele não mede qualidade semântica de uma resposta livre nem prova que a base sintética representa uma pessoa real.

## Execução

Requer `google-cloud-bigquery` e Application Default Credentials (ADC) com leitura na tabela. Não usa chave de API. As consultas desativam o cache para que o guard confira o estado atual da fonte. Da raiz do backend, com o ambiente Python da solução:

```powershell
..\.venv\Scripts\python.exe skills/extracao-comportamental-iai/scripts/preparar_extracao.py --evidencia skills/extracao-comportamental-iai/evidencias/clique-unico.json
..\.venv\Scripts\python.exe skills/extracao-comportamental-iai/scripts/validar_resposta.py --evidencia skills/extracao-comportamental-iai/evidencias/clique-unico.json --proposta proposta-do-agente.json
python skills/extracao-comportamental-iai/scripts/testar_skill.py
```

O primeiro comando grava uma evidência com horário, fonte, corte, número do sorteio, UUID, linha e valor sorteados, hash, consultas, `job_id`, bytes e duração; imprime a proposta esperada para compor a chamada do agente. Se a preparação falhar, grava `NAO_MEDIDO` com o motivo quando o caminho estiver gravável. A carga conversacional para o LLM continua sendo somente o texto inicial do usuário, conforme o contrato existente de `primeira-chamada`; dados da extração ficam na etapa posterior do IAI. Use caminho de evidência único por clique e não envie esse JSON ao usuário.

O segundo comando relê também a lista de UUIDs para conferir a posição sorteada e grava a decisão e a duração do guard. Somente em aprovação imprime `{aprovado, id_extracao, numero_usuario, id_usuario, resposta}`. Proposta errada gera `REPROVADO`; falha de leitura gera `NAO_MEDIDO`. Ambas saem com código diferente de zero e não imprimem resposta pública. Evidências locais ficam em `evidencias/`, ignorado pelo Git; revise privacidade antes de exportá-las.

```text
clique IAI → UUID e movimento sorteados no BigQuery → evidência inicial
          → proposta JSON do agente → releitura BigQuery → guard → evidência final
          → texto público somente se aprovado
```
