# Documentação dos Templates e Variáveis de Comunicação

## 1. Variável 1: Conversa Pré-Preenchida (Chat)
A primeira variável é montada a partir do gênero do cliente derivado do `numero_id`:
- **Gênero F (Feminino)**: Arquivo `templates/recommendations/chat_f.html`.
  - Abordagem: "Planejamento e Oportunidades Personalizadas"
  - Linguagem: Foco em autonomia patrimonial, segurança familiar e diversificação consciente.
  - Gatilho final: Pergunta de estímulo que precede o botão **"E agora?"**.
- **Gênero M (Masculino)**: Arquivo `templates/recommendations/chat_m.html`.
  - Abordagem: "Otimização Financeira e Performance de Capital"
  - Linguagem: Foco em performance de capital de giro, limites estratégicos e rentabilidade ativa.
  - Gatilho final: Pergunta de estímulo que precede o botão **"E agora?"**.

## 2. Ação Intermediária: O Botão "E agora?"
- O botão atua como disparador do evento de transição de estado da Tela 2 para a Tela 3.
- Envia o payload de contexto do cliente para o endpoint `/api/v1/comunicacao/e-agora/<id>/`.

## 3. Variável Template 3: Planilha Fixa de Dados
A interface de comunicação é respondida com a matriz fixa de produtos bancários Itaú:
1. **CDB Itaú Personalizado Pós-Fixado** (Investimentos, 104% a 112% CDI)
2. **Crédito Sob Medida com Taxa Bonificada** (Crédito, a partir de 1,19% a.m.)
3. **Cartão Itaú Carbon Platinum / Black** (Meios de Pagamento, Cashback/Pontos)
4. **Previdência & Planejamento Sucessório** (Previdência, PGBL/VGBL)
5. **Seguro Vida & Proteção Integrada** (Seguros, Assistência 24h)

Cada linha da planilha é ponderada pelo **Score Comportamental** do cliente para calcular um índice de adesão (`score_propensao_cliente`), definindo a ordenação da tabela.

## 4. Contextualização do Agente de Prompt
O template injeta diretamente os metadados que controlam o comportamento do agente de IA na Batalha de Agentes:
```text
[SISTEMA: AGENTE ITAÚ BATALHA DE AGENTES TIME 2]
INDICE_CORTE: {indice_code} | NIVEL_PROPENSAO: {nivel} (Score: {score}/1000)
CLIENTE_ID: {id} | NOME: {nome} | GENERO: {genero}
DIRETRIZ_COMPORTAMENTAL: {diretriz_comportamental}
FOCO_ESTRATEGICO: {foco_estrategico}
TOM_VOZ: {tom_comunicacao}
GATILHO_OPERACIONAL: {gatilho_acao}
GUARDRAIL: Nunca prometer rentabilidade garantida e manter conformidade estrita com normas Bacen/CVM.
```
