# Arquivo de desafio_itau/politica

| Data | Ficheiro arquivado | Substituído por | Motivo |
|---|---|---|---|
| 2026-09-27 | `2026-09-27/erros_api-v1-1.1.0.json` | `erros_api-v1.json` 1.2.0 | Tabela `tipos` (código de máquina estável para o front), 400 do provedor sem nova chamada, router de modelos (backend-22, pedido do dono 12:38/12:39 BRT). |
| 2026-09-27 | `2026-09-27/erros_api-v1-1.2.0.json` | `erros_api-v1.json` 1.3.0 | Tipo `resposta_modelo_invalida` (saída cortada/fora do schema) com a linha 503 em vez de NAO_CLASSIFICADO; router segue ao próximo modelo em resposta inválida (backend-22, coordenador 13:09 BRT). |
