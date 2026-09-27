# Arquivo de desafio_itau/politica

| Data | Ficheiro arquivado | Substituído por | Motivo |
|---|---|---|---|
| 2026-09-27 | `2026-09-27/erros_api-v1-1.1.0.json` | `erros_api-v1.json` 1.2.0 | Tabela `tipos` (código de máquina estável para o front), 400 do provedor sem nova chamada, router de modelos (backend-22, pedido do dono 12:38/12:39 BRT). |
| 2026-09-27 | `2026-09-27/erros_api-v1-1.2.0.json` | `erros_api-v1.json` 1.3.0 | Tipo `resposta_modelo_invalida` (saída cortada/fora do schema) com a linha 503 em vez de NAO_CLASSIFICADO; router segue ao próximo modelo em resposta inválida (backend-22, coordenador 13:09 BRT). |
| 2026-09-27 | `2026-09-27/erros_api-v1-1.3.0.json` | `erros_api-v1.json` 1.4.0 | Troca de modelo por erro do provedor dentro do prazo do turno (limite `troca_de_modelo_no_turno`), pedido do dono 12:39; 503 real do dono às 13:35 com 18 s livres (backend-22). |
| 2026-09-27 | `2026-09-27/cotas-gemini-v1-1.0.0.json` | `cotas-gemini-v1.json` 1.1.0 | Bloco `capacidades` por modelo lido pelo router; timeout/5xx com resfriamento transitório de 15 s e último recurso (backend-22, dono 14:09/14:11 BRT). |
