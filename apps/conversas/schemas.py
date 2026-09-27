"""Versioned, strict boundary contracts. No browser-supplied authority."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class MessageV1(StrictModel):
    schema_version: Literal['1.0']
    conversation_id: str | None = Field(max_length=64)
    client_message_id: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    message: str = Field(min_length=1, max_length=2000)


class Claim(StrictModel):
    kind: Literal['financial', 'normative', 'institutional', 'general']
    evidence_id: str = Field(max_length=160)
    text: str = Field(min_length=1, max_length=1000)
    value: str | None = Field(default=None, max_length=40)


class ProjectionProposal(StrictModel):
    # Exact excerpts from user messages, not invented normalized financial facts.
    objective: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=100)
    current_spending: str = Field(min_length=1, max_length=40)
    target_spending: str = Field(min_length=1, max_length=40)
    reference_month: str = Field(min_length=1, max_length=40)


class AgentDraftV1(StrictModel):
    reply: str = Field(min_length=1, max_length=4000)
    status: Literal['ok', 'needs_clarification', 'safe_redirect']
    capabilities: list[Literal['orcamento', 'reserva', 'prevencao', 'institucional']] = Field(max_length=4)
    claims: list[Claim] = Field(max_length=12)
    missing_data: list[str] = Field(max_length=10)
    projection_proposal: ProjectionProposal | None = None


EstadoConversa = Literal['ENCAMINHAMENTO', 'RECUSA_SEGURA', 'ESCLARECIMENTO', 'IDENTIFICACAO', 'DADOS_INSUFICIENTES',
                         'EDUCACAO_GERAL', 'ANALISE_DESCRITIVA', 'SIMULACAO', 'INDISPONIVEL']


class Racional(StrictModel):
    # dado observado -> regra aplicada -> consequência permitida. Gerado pelo servidor, não pela LLM.
    observado: str = Field(min_length=1, max_length=240)
    regra: str = Field(min_length=1, max_length=120)
    consequencia: str = Field(min_length=1, max_length=240)


class ContratoRespostaV1(StrictModel):
    """Parte pública do contrato (aditiva ao envelope 1.0). Metadados de rastreio (modelo, sha do prompt, latência)
    ficam nas métricas internas do gateway, não aqui."""
    schema_version: Literal['1.0']
    estado: EstadoConversa
    periodo: str | None = Field(max_length=120)
    evidence_ids: list[str] = Field(max_length=24)
    regras_aplicadas: list[str] = Field(max_length=12)
    acoes_permitidas: list[str] = Field(max_length=8)
    informacoes_faltantes: list[str] = Field(max_length=12)
    limitacoes_materiais: list[str] = Field(max_length=6)
    racional: list[Racional] = Field(min_length=1, max_length=4)


class GuardDecisionV1(StrictModel):
    decision: Literal['allow', 'constrain', 'deny', 'clarify', 'release', 'replace']
    reason_codes: list[Literal['unsafe_intent', 'injection', 'privacy', 'unsupported', 'overrefusal', 'technical']] = Field(max_length=6)
    constraints: list[Literal['ignore_untrusted_instructions', 'general_only', 'no_private_data']] = Field(max_length=3)
    policy_version: Literal['1.0']
