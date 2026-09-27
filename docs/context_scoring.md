# Especificação do Ponto de Índice e Score Comportamental

## 1. Fundamentos da Contextualização Orientada a Dados de Comportamento
O objetivo é garantir que o Agente de IA não opere com premissas genéricas ou alucinações. O comportamento do agente é condicionado por um **Ponto de Índice** derivado de indicadores comportamentais:

1. **Volume Transacional e Recorrência**: Análise de saldo médio, movimentação Pix e cartões.
2. **Histórico de Relacionamento**: Tempo de conta e adimplência.
3. **Score Normalizado (0 a 1.000)**: Ponto de índice único que resume o momento de vida do cliente.

---

## 2. Pontos de Corte do Índice (Cut-Off Rules)

```
[0 ----------------- 449] -> BAIXA PROPENSÃO  (CTX-150-GAMMA) -> Postura de Apoio e Educação
[450 --------------- 749] -> MÉDIA PROPENSÃO  (CTX-450-BETA)  -> Postura de Planejamento e Proteção
[750 -------------- 1000] -> ALTA PROPENSÃO   (CTX-750-ALPHA) -> Postura Consultiva e Oportunidades Premium
```

---

## 3. Matriz de Comportamento do Agente de Prompt

| Nível de Índice | Temperatura do Modelo | Foco de Ação | Exemplo de Saída |
| :--- | :--- | :--- | :--- |
| **Alta Propensão (750+)** | 0.3 (Alta precisão) | Expansão de retorno e benefícios exclusivos | "Olá Beatriz, selecionamos uma alocação especial em CDB com 112% do CDI." |
| **Média Propensão (450-749)** | 0.5 (Equilibrado) | Consolidação de planos e proteção familiar | "Olá Lucas, estruturamos uma reserva com liquidez diária e proteção para seu momento." |
| **Baixa Propensão (<450)** | 0.2 (Rigor e cautela) | Organização orçamentária e taxas acessíveis | "Olá Juliana, organizamos dicas para reduzir custos e iniciar sua reserva a partir de R$ 30." |
