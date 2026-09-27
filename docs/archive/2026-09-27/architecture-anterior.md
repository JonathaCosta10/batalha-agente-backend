# Arquitetura do Projeto: Desafio Itaú - Batalha de Agentes (Time 2)

## 1. Visão Geral
Este projeto implementa uma solução em duas frentes:
1. **Front-End Android Demo**: Aplicativo em modo simulador mobile Android com 3 camadas/telas integradas:
   - **Tela 1**: Interface minimalista padrão Itaú com acionador floating action button (FAB) em formato de **estrela** no canto inferior direito.
   - **Tela 2**: Conversa pré-preenchida (**Variável 1**) com bifurcação estrita de texto entre os gêneros **F** (Feminino) e **M** (Masculino), baseada no ID do cliente (1 a 1.000). Ao final, conta com o botão interativo **"E agora?"**.
   - **Tela 3**: Interface de comunicação acionada pelo botão "E agora?", renderizando a **Variável Template 3** (Planilha fixa de produtos bancários e regras de negócio) e o **Ponto de Índice** comportamental para contextualização do Agente de Prompt.
2. **Back-End Django (`desafio-itau-batalha-de-agentes-time2`)**:
   - Módulo com separação clara de templates (`templates/recommendations/`)
   - Documentação de templates (`docs/templates/`)
   - Configuração de redirecionamento do projeto raiz para o aplicativo (`RedirectView`)
   - Roteamento organizado de URLs RESTful e Views de renderização server-side
   - Isento de configuração manual de banco de dados (persistência leve em memória e matrizes fixas)
   - Espaço para notebooks de regras (`notebooks/regras_batalha_agentes.ipynb`)

---

## 2. Mapa de Rotas e URLs

| Método | Rota | Descrição |
| :--- | :--- | :--- |
| `GET` | `/` | Redirecionamento automático para `/app/` |
| `GET` | `/app/` | Dashboard central com visão geral do Time 2 |
| `GET` | `/app/chat/<id>/` | Renderização do template HTML de chat para o cliente |
| `GET` | `/app/comunicacao/<id>/` | Renderização da interface de comunicação com a matriz fixa |
| `GET` `POST` | `/api/v1/chave-interacao-tela-iai/` | Consulta ou alterna a chave ON/OFF (texto neutro × F/M) |
| `GET` | `/api/v1/cliente/random/` | Retorna login randômico entre os 1.000 clientes da base (`?genero=F\|M`) |
| `GET` | `/api/v1/cliente/<id>/` | Retorna dados completos do cliente por ID (1..1000) |
| `GET` | `/api/v1/grupos-fixos/` | Estatísticas e amostras dos grupos fixos de clientes |
| `GET` | `/api/v1/chat/variavel-1/<id>/` | Retorna o texto pré-preenchido ativo (neutro, F ou M, conforme a chave) |
| `GET` `POST` | `/api/v1/comunicacao/e-agora/<id>/` | Disparo do "E agora?" com Template 3 e contexto do agente |
| `GET` | `/api/v1/contexto-score/<id>/` | Retorna o Ponto de Índice e diretriz comportamental do agente |
| `GET` | `/api/v1/planilha-fixa/` | Retorna os itens brutos da planilha fixa de produtos |
| `GET` | `/context-agent/` | Painel HTML do agente contextualizado |
| `GET` | `/api/v1/context-agent/status-harness/` | Auditoria: rotas YAML, provedores, status da chave (mascarada), tese e evals |
| `POST` | `/api/v1/context-agent/enviar-mensagem/` | Conversa contextualizada com o agente (sessão, roteamento, negociação de modelo, eval) |
| `POST` | `/api/v1/context-agent/primeira-chamada/` | Envia só `{texto_inicial}` ao Gemini; única rota chamada pelo front |

> As rotas de `apps.recomendacao` respondem em `/app/` e em `/api/v1/`; as de `apps.context_agent_datadriven` em `/context-agent/` e em `/api/v1/context-agent/`. O proxy do Vite encaminha só `/api/v1/context-agent`. Fluxos entre telas: [`fluxos-de-conversacao.md`](fluxos-de-conversacao.md). Contratos: [`inteirações-cloud/27-09-2026/INDICE.md`](inteirações-cloud/27-09-2026/INDICE.md).

---

## 3. Recorte de Clientes & Regras de Negócio (1.000 Perfis)
- **Login Randômico**: Permite simular interações dinâmicas selecionando qualquer um dos 1.000 clientes.
- **Derivação de Gênero pelo ID**:
  - `ID % 2 == 0` $\rightarrow$ **Feminino (F)**
  - `ID % 2 != 0` $\rightarrow$ **Masculino (M)**
- **Ponto de Índice de Corte (Score 0 a 1.000)**:
  - $\ge 750$: Alta Propensão (`CTX-750-ALPHA`) $\rightarrow$ Tom executivo, consultivo e proativo.
  - $450$ a $749$: Média Propensão (`CTX-450-BETA`) $\rightarrow$ Tom orientador e equilibrado.
  - $< 450$: Baixa Propensão (`CTX-150-GAMMA`) $\rightarrow$ Tom acolhedor e focado em controle básico de despesas.
