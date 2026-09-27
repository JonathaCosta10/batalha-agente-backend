"""
Nomes dos modelos Google Gemini usados pelo agente — fonte única.

2026-09-27, medido com a chave do projeto (.secrets:API_KEY_SECRECT):
- gemini-2.5-flash-lite e gemini-2.5-flash -> HTTP 404 "no longer available to new users";
  a própria Google indica gemini-3.5-flash-lite como substituto.
- gemini-3.5-flash-lite -> 200 (~700 ms); gemini-flash-latest -> disponível, mas 503 em pico de demanda.
Trocar um modelo é mudar este arquivo (e o YAML de rotas, que tem valor literal).
"""

# Rota direta do front: só o texto inicial vai ao modelo.
MODELO_PRIMEIRA_CHAMADA = "gemini-3.5-flash-lite"

# Tentado pelo agente quando o modelo primário da rota falha.
MODELO_CONTINGENCIA = "gemini-3.5-flash-lite"

# Modelos homologados para o provedor Google, em ordem de prioridade.
# Ordem invertida em 2026-09-27 09:35 BRT (I2, recomendação aceita pelo dono às 09:28). Ledger
# relatorios/avaliacoes/2026-09-27.jsonl: gemini-flash-latest 429 em 19/19 tentativas; gemini-3.5-flash-lite
# 32 aprovadas + 2 reprovadas pelos guards (200), 1x 429, p50 1250 ms. Com a ordem antiga, todo turno de
# interacao/ gastava uma chamada perdida em 429 antes do modelo com cota. Nenhum modelo foi trocado nem removido.
MODELOS_GOOGLE = ["gemini-3.5-flash-lite", "gemini-flash-latest"]

# Registro da integração efetiva (verificado em 2026-09-27; nada aqui muda o comportamento).
# DIVERGÊNCIA: o pedido de 2026-09-27 fala em "Gemini 3.8"; o código chama gemini-3.5-flash-lite (e
# gemini-flash-latest). Nenhuma chamada a um "3.8" existe no código. docs/interacoes-front-back.md registra
# gemini-3.8-flash -> HTTP 429 (FreeTier, 20 pedidos/dia) com a chave do projeto. O modelo NÃO foi trocado.
INTEGRACAO = {
    "provedor": "Google Gemini API (AI Studio)",
    "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
    "sdk": "nenhum: urllib (REST) em apps/conversas/gateway.py; chave no header x-goog-api-key",
    "generation_config_conversas": {
        "temperature": "não enviada -> padrão do provedor (guia Gemini 3, atualizado 2026-09-23: manter 1.0)",
        "thinkingConfig": {"thinkingLevel": "LOW"},
        "responseMimeType": "application/json", "candidateCount": 1,
    },
    "seed": "não enviada; mesmo com seed o texto não é reproduzível: textos críticos saem de templates do servidor",
    "divergencias_de_amostragem": [
        "agentes/LLM_Models/google/cliente.py: temperature 0.35 (rota legada enviar-mensagem)",
        "services/agente_service.py: temperature 0.4; rotas_base.yaml: 0.30/0.35",
    ],
    "evidencia_model_version": "relatorios/avaliacoes/2026-09-27.jsonl: modelVersion 'gemini-3.5-flash-lite' em 34 "
                              "tentativas; gemini-flash-latest HTTP 429 em 19",
}
