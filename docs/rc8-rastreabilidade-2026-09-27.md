# Matriz de rastreabilidade — Resolução Conjunta nº 8/2023 (BCB/CMN)

> **O que esta matriz é:** um mapa de engenharia que liga os dispositivos da RC 8 aos controles do protótipo.
> **O que ela não é:** parecer jurídico nem declaração de conformidade.
> O protótipo não é canal oficial do Itaú.
> Toda linha "responsável" está **PENDENTE** até haver um dono institucional nomeado.

- **Texto usado:** `apps/conversas/knowledge/resolucao-conjunta-08-2023.json`. Foi conferido com a API oficial do BCB em
  2026-09-27T08:34:53-03:00 por `scripts/conferir_rc8_oficial.py`.
  - Resultado: 6 artigos IGUAL_AO_OFICIAL; o art. 3º ficou IGUAL_SALVO_ESPACOS.
  - Evidência: `relatorios/normas/rc8-conferencia-2026-09-27.json` (sha256 da resposta bruta e7ca0e82…329e).
- **Alteração posterior:** a RC 20/2026 altera o art. 3º § 1º a partir de 2027-07-01
  (`apps/conversas/knowledge/resolucao-conjunta-20-2026.json`). A matriz vale para a redação vigente em 2026-09-27.
- **Legenda da coluna "tipo":**
  - **LITERAL** — o texto da norma diz.
  - **INTERPRETAÇÃO** — leitura do time, não validada juridicamente.
  - **ESCOLHA** — decisão de engenharia que a norma não exige.

| Dispositivo | Tipo | Obrigação (como lida) | Controle no protótipo | Teste | Evidência | Responsável |
|---|---|---|---|---|---|---|
| Art. 1º | LITERAL | Escopo: instituições autorizadas pelo BCB. | Nenhum. O protótipo não é instituição e não se apresenta como tal (`comunicacao-v1.json` → `aviso`). | — | — | PENDENTE |
| Art. 2º caput | LITERAL | Adotar medidas de educação financeira para pessoas naturais. | O chat é descritivo e educativo. Os estados `EDUCACAO_GERAL` e `ANALISE_DESCRITIVA` estão em `apps/conversas/estado.py`. | `test_estado_contrato.Roteamento` | 303 OK + 1 falha esperada (2026-09-27) | PENDENTE |
| Art. 2º § 1º I | LITERAL → INTERPRETAÇÃO | Contribuir para a organização e o planejamento do orçamento. | Médias de entradas/saídas e a referência 50/30/20, que é **orientação, não norma** (`operacional-v1.json` → `orcamento.referencia_50_30_20`). Números só saem com fonte (`estado.numeros_sem_fonte`). | `Roteamento.test_prova_negativa_numero_sem_fonte_nao_sai`, `test_politica_operacional.Equivalencia` | idem | PENDENTE |
| Art. 2º § 1º II | LITERAL → INTERPRETAÇÃO | Contribuir para poupança e resiliência. | A simulação usa hipóteses de redução de 5% e 8% (`projecao.hipoteses_reducao`), rotuladas como hipótese e não como promessa. O léxico bloqueia "garantia". | `test_lexico_e_erros_api` (promessa) | idem | PENDENTE |
| Art. 2º § 1º III | LITERAL → INTERPRETAÇÃO | Contribuir para prevenir inadimplemento e superendividamento. | `divida.relevante`: dívida ≥ 10% das entradas **ou** ≥ 1 multa. Comparação exata antes do arredondamento; indicador ausente vira NAO_MEDIDO. | `Limites.test_exatamente_10_pct`, `…9_96…`, `…nulo_nao_medido` | idem | PENDENTE |
| Art. 2º § 2º | LITERAL | O consorciado é cliente. | Não aplicável: não há consórcio no protótipo. A contratação é recusada (corpus c20). | corpus c20 (NÃO EXECUTADO) | — | PENDENTE |
| Art. 3º caput | LITERAL | Política baseada em ética, responsabilidade, transparência e diligência. | Transparência via contrato público (`ContratoRespostaV1`: estado, evidence_ids, período, racional observado→regra→consequência). | `Roteamento.test_analise_descritiva_com_fato_medido` | idem | PENDENTE |
| Art. 3º I (valor) | INTERPRETAÇÃO | Ações úteis e relevantes. | Não medido. A rubrica humana de utilidade (0–2) está no corpus. | — | NÃO EXECUTADO | PENDENTE |
| Art. 3º II (alcance) | INTERPRETAÇÃO | Acesso ao universo de clientes. | Fora do escopo de engenharia do protótipo. | — | — | PENDENTE |
| Art. 3º III (adequação) | INTERPRETAÇÃO + ESCOLHA | Linguagem, canal e momento adequados ao perfil. | Os perfis de comunicação mudam só extensão, vocabulário e exemplos, **nunca permissões** (`comunicacao-v1.json` → `regra_dos_perfis`). O bordão fica vedado em acolhimento. | `test_comunicacao_e_corpus.DerivaComunicacao`, `Invariancia.test_parafrase…` | idem | PENDENTE |
| Art. 3º § 1º I | INTERPRETAÇÃO | Considerar as fases do relacionamento. | Não implementado. | — | — | PENDENTE |
| Art. 3º § 1º II | INTERPRETAÇÃO | Compatível com a complexidade dos produtos. | O chat não recomenda produto. Os catálogos de produto sem fonte (inventário de 2026-09-27) ficam fora da conversa, e o léxico bloqueia "pré-aprovado". | `test_lexico_e_erros_api` | idem | PENDENTE |
| Art. 3º §§ 2º–3º | LITERAL | Unificação por conglomerado e formalização em conselho. | Institucional: fora da engenharia. | — | — | PENDENTE |
| Art. 4º I | LITERAL | Mecanismos que assegurem a implementação. | A política é versionada (`operacional-v1.json` com rule_id@versão, sha256). A referência da regra vai no contrato. Guard AST: sem `eval`. | `test_politica_operacional.SemEval` (com prova negativa) | idem | PENDENTE |
| Art. 4º II | LITERAL → ESCOLHA | Monitorar cumprimento e efetividade com métricas. | Métricas por chamada no gateway (modelo, modelVersion, tokens, outcome, versão da política). Ledger em `relatorios/avaliacoes/`. Protocolo de 30×5 em `scripts/avaliar_llm.py`. | `Corpus.test_resumo_calcula_metricas…` | Execução real **NÃO EXECUTADA** | PENDENTE |
| Art. 4º III | LITERAL → ESCOLHA | Identificar e corrigir ineficiências. | No máximo uma correção controlada, seguida de fallback seguro. Erros de API 400/404/429/503/504 são tratados por tabela (`erros_api-v1.json`). | `test_lexico_e_erros_api` (gateway/serviço) | idem | PENDENTE |
| Art. 5º | LITERAL | Diretor responsável indicado ao BCB. | Institucional. | — | — | PENDENTE |
| Art. 6º | LITERAL | Competência do BCB. | — | — | — | — |
| Art. 7º | LITERAL | Vigência a partir de 2024-07-01. | `temporalidade` no JSON da norma. | — | — | — |

**Limite.** Cobertura por teste significa que o controle de engenharia existe e reprova o caso ruim sintético.
Isso não significa que a obrigação normativa foi cumprida: essa conclusão exige validação jurídica e dono institucional.
