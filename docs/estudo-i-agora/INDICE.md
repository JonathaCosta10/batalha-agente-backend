# Estudo i.agora — índice

Estudo da colega (Colab `i.agora-checkpoint.ipynb`) que fundamenta o agente: raio-X comportamental, calibração do perfil, coorte de dezembro e matriz de produtos. Esta pasta guarda a cópia local, o catálogo das consultas e a **medição das afirmações na tabela real do BigQuery**.

| Documento | Conteúdo |
| --- | --- |
| [Origem da cópia](../../notebooks/estudo-i-agora/ORIGEM.md) | Notebook local byte a byte, SHA-256, datas e o que faltou (o CSV). |
| [Catálogo de consultas](consultas.md) | C01-C13: célula, fonte (`REAL`/`FALLBACK`/`SINTETICO`/`FIXO`), regra, número do notebook × número medido. |
| [SQL das medições](sql/) | `q01`-`q06` sobre `hackathon_dados.extrato_sintetico`, mais o executor `medir.py`. |
| [Fluxo de um usuário](sql/q07_fluxo_usuario.sql) | Consulta `q07` parametrizada por UUID e data de corte; [medidor](sql/medir_usuario.py) com tempo e checagens, sem misturar o ID inteiro da demo. |
| [T3 e faixa de resposta](t3-e-resposta.md) | Vulnerável / Esbanjador / Livre por Inflow/Outflow/Surplus: estatística aplicada (IC bootstrap, sensibilidade do limiar, Spearman), faixa de tom e sentimento por segmento, visões por assunto e guard que reexecuta a query. |
| [Medições 2026-09-27](medicoes/2026-09-27/) | Resultado selado de cada consulta (fonte, hora BRT, `job_id`, bytes), mais `estatistica_t3.json` e `guard_e2e.json` (`sql/medir_t3.py`). |
| [Schemas](schemas/) | `extrato-sintetico.schema.json` (linha da tabela), `medicao.schema.json` (arquivo selado), `envio-agente.schema.json` e `veredito-guard.schema.json` (contrato do guard). |
| Código | `apps/context_agent_datadriven/pastas_raiz/estudos/i_agora/consultas.py` e `tests/test_consultas_i_agora.py` (11 testes, 5 provas negativas); `t3.py`, `visoes.py`, `guard.py`, `estatistica.py`, `sql/visao_*.sql` e `tests/test_t3_guard_i_agora.py` (23 testes). |

## Fluxo do estudo (os 4 passos do notebook)

```
Passo 1 · Raio-X (C01-C09)  ──▶  Passo 2 · Calibração (C13)  ──▶  Passo 3 · Coorte de dezembro (C10-C12)  ──▶  Passo 4 · Matriz de produtos (C08, C13)
extrato → mensal → cluster        prioridade, risco, tom           dívida, score, meta em 6 meses            cluster → produto Itaú
```

## Onde entra no fluxo de contextualização do agente

O agente atual (`docs/architecture.md`) não lê nada deste estudo. A tabela diz onde cada saída se encaixaria e o que falta para isso.

| Saída do estudo | Função em `consultas.py` | Destino no agente | Estado |
| --- | --- | --- | --- |
| Base de 1.000 clientes, corte em 22/12/2025 | `normalizar_extrato` | `TESE_COMPLETA_CONTEXTUALIZADA.fontes_de_evidencia` e `regras_corte_temporal` (`pastas_raiz/docs/tese_agente_docs.py`) | A tese já declara "1.000 clientes", o que confere com q01. A tabela tem 7.956 linhas depois do corte, e nenhuma consulta as filtra ainda. |
| `cluster_financeiro` | `perfil_anual` / `classificar_saude` | Linha `NIVEL_PROPENSAO` do prompt do Template 3 (`templates/template_docs.md` §4) | Medido (q03): 49,3 / 27,9 / 22,8. Ainda não está ligado. |
| Segmento T3 e faixa de tom | `t3.classificar_t3`, `t3.PERFIS_DE_RESPOSTA` | `TOM_VOZ` e `FOCO_ESTRATEGICO`; guard antes de enviar | Medido: 45,3 / 28,6 / 26,1. Regra proposta, a validar. Guard provado no BigQuery, ainda não ligado ao `primeira_chamada.py`. |
| `divida_atual`, `meta_de_economia_mensal` | `coorte_negativada`, `meta_de_economia_mensal` | `GATILHO_OPERACIONAL` do prompt | Medido (q04): 316 clientes, dívida mediana R$ 1.638,49. |
| `score_de_flexibilidade_pct` | `score_de_flexibilidade` | `DIRETRIZ_COMPORTAMENTAL` | **Bloqueado**: falta decidir quais macros reais são flexíveis ou supérfluas. |
| Produto recomendado | `recomendar_produto` | `FOCO_ESTRATEGICO`; guardrail Bacen/CVM | Taxas digitadas (1,49% a.m., 100% CDI) **sem fonte**, e o guardrail proíbe prometer rentabilidade. |
| Calibração (prioridade, risco, tom) | — | `TOM_VOZ` | Só há a persona fixa "Marina", sem questionário. |

## Autenticação no BigQuery (verificada em 2026-09-27)

- Método: **Application Default Credentials**. A política da organização veda chave de API.
- Credencial: `%APPDATA%\gcloud\application_default_credentials.json`, tipo `authorized_user`, `quota_project_id = batalha-time-02-lxof`. O token é emitido (`gcloud auth application-default print-access-token` passou).
- Acesso: `bq ls` mostra o dataset `hackathon_dados` com uma tabela, `extrato_sintetico`. As 6 consultas rodaram com o cliente Python `google-cloud-bigquery`.
- O Cloud SDK está em `%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin`, **fora do PATH**. Sem ele no PATH, o `bq` falha com `WinError 2` ao buscar a credencial.
- Máquina nova: `gcloud auth application-default login` e depois `gcloud auth application-default set-quota-project batalha-time-02-lxof`. O script `setup_adc.sh` do Google é interativo e feito para Linux/macOS; não foi usado aqui.

## Reproduzir

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe docs\estudo-i-agora\sql\medir.py          # grava medicoes\<hoje>\
$env:PYTHONPATH = '.'; ..\.venv\Scripts\python.exe -m unittest tests.test_consultas_i_agora -v
```

O nome da tabela é `extrato_sintetico`: os dados são **sintéticos**, gerados para o hackathon. "Medido" aqui quer dizer medido nessa base, não em clientes reais.
