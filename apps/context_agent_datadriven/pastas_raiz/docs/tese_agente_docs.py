"""
Pastas Raiz: Documentação Original e Evidências da Tese do Agente Itaú.
Este repositório interno consolida os artefatos de dados e teses do projeto.
"""

TESE_COMPLETA_CONTEXTUALIZADA = {
    "versao_tese": "2.4.0-datadriven",
    "data_corte": "2025-12-22",
    "premissas_fundamentais": [
        "O cliente não deve ser sobrecarregado com números ou scores na interface conversacional.",
        "A tomada de decisão é governada pelo Harness antes de qualquer prompt atingir a LLM.",
        "Os dados transacionais e comportamentais operam como memória ativa e não como display.",
    ],
    "regras_corte_temporal": {
        "data_fixa": "2025-12-22",
        "faixa_horario": "00:00:00 às 23:59:59 BRT",
        "descricao": "Nenhum dado posterior a 22/12/2025 pode ser inferido pelo agente.",
    },
    "fontes_de_evidencia": [
        "Extrato unificado de conta corrente e poupança",
        "Padrão de utilização de limite de crédito e adiantamento a depositante",
        "Histórico de movimentações Pix e pagamento de contas essenciais",
        "Recorte amostral determinístico de 1.000 clientes com distribuição calibrada",
    ]
}
