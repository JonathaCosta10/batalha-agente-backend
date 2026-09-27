# Registro para a seção Claude irmã — extração IAI

## Documentação da fronteira

A skill [extração comportamental IAI](../../skills/extracao-comportamental-iai/SKILL.md), no commit local `922ed70`, especifica o sorteio e o guard anteriores à publicação da resposta. O [contrato JSON](../../skills/extracao-comportamental-iai/contrato-de-extracao-e-resposta.json) define a fonte, os campos e a forma de retorno.

```text
clique IAI → número ordinal + UUID sorteados → linha de extrato + vlr sorteados
          → proposta JSON do agente → releitura BigQuery sem cache
          → guard factual e estrutural → resposta em texto ou recusa
```

O número ordinal identifica a posição sorteada na lista ordenada de UUIDs **naquele clique**. Ele não corresponde ao `cliente_id` inteiro do app demo. A fonte é `batalha-time-02-lxof.hackathon_dados.extrato_sintetico`, uma base sintética. O comportamento observado nesta skill é `tipo` (`E`/`S`) e `nom_cate_macro` da linha sorteada; a informação numérica publicada é `vlr`, sem normalização. A data de corte é **2025-12-22** em `America/Sao_Paulo`.

Esta skill não substitui a segmentação T3 e o guard de visões agregadas descritos em [T3 e resposta](t3-e-resposta.md). O contrato daqui trata **uma linha sorteada** e a conferência exata dessa linha. A seção Claude irmã pode citar este arquivo ao fechar a documentação, preservando essa distinção. Nenhuma mudança de integração no botão, na view ou no prompt foi feita por esta seção. Os materiais pessoais em `.claude/` permanecem locais e não são requisito da solução publicada.

## Evidência de fechamento

Medição em **2026-09-27 04:27 BRT**, fonte BigQuery acima, com cache desativado e ADC. O preparo consultou os UUIDs e o extrato de um UUID; o guard repetiu ambas as consultas. A proposta usada na prova real foi **simulada a partir da evidência**, não uma saída de LLM.

| Etapa | Tempo medido | Bytes processados | Jobs BigQuery |
| --- | ---: | ---: | --- |
| Preparo | 4.108,423 ms | 58.610.568 | `5756aad3-ab1d-4c9c-9632-d82d9cdb5ef2`, `080ad7f3-fc20-43c7-a729-2302a807c322` |
| Guard | 5.243,805 ms | 58.610.568 | `8b64134c-93c4-4cbe-b960-6d8707f298a9`, `f0b3da4e-4806-4824-b483-2fb4dffac2c3` |

O guard aprovou o valor `19.22` da linha sorteada. Os **8 testes locais** da skill cobrem aprovação e recusa de fato inventado, número trocado, chave extra, linha alterada, nulo e falha de consulta. A evidência individual está em `skills/extracao-comportamental-iai/evidencias/validacao-final-20260927.json`; essa pasta é local e ignorada pelo Git.

## Estado para encerramento

- **Feito:** skill, contrato, scripts, evidência local e prova positiva/negativa; commit `922ed70`.
- **Pendente de outra seção:** conectar o botão IAI e a chamada do agente a esse contrato. Até lá, não afirmar que a interface usa a skill.
- **Limite da prova:** estrutura e fato da linha sorteada foram comparados; qualidade semântica de texto livre de um LLM permanece `NAO_MEDIDO`.
- **Canal de handoff:** tentativa de comunicado em `hub_local` não foi enviada: o emissor recusou `--from itau-agentes` porque esse projeto não consta nas filas registradas. Este arquivo fica como registro compartilhado para a seção Claude irmã; não há confirmação de leitura por ela.
