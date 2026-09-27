"""Gemini no servidor: dois guards + um gerador, por HTTP (sem google-genai/ADK).

Portado de agente-app-mobile/agent_backend/conversation/gateway.py (commit 1302ba5). O original usa o
SDK google.genai e o Runner do ADK; aqui a chamada é a mesma REST `generateContent` que o backend já usa
em `agentes/LLM_Models/google/cliente.py`, com chave de `desafio_itau.segredos.obter_api_key()` e nomes
de modelo de `desafio_itau.modelos_llm`. Mantém do original: saída JSON com schema, sem ferramentas, sem
retry do provedor, candidato único terminado em STOP, orçamento de chamadas por processo, métricas sem
conteúdo nem chave. A chave vai no header `x-goog-api-key`, nunca na URL.
"""
import asyncio
import json
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone

from desafio_itau.modelos_llm import MODELO_CONTINGENCIA, MODELO_PRIMEIRA_CHAMADA, MODELOS_GOOGLE
from desafio_itau.segredos import obter_api_key
from desafio_itau import politica
from desafio_itau.politica import erros_api

from .prompts.renderer import render_prompt
from .schemas import AgentDraftV1, GuardDecisionV1

URL = 'https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent'
ALLOWED_MODELS = set(MODELOS_GOOGLE) | {MODELO_PRIMEIRA_CHAMADA, MODELO_CONTINGENCIA}
SAFETY = [{'category': c, 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'} for c in (
    'HARM_CATEGORY_HATE_SPEECH', 'HARM_CATEGORY_DANGEROUS_CONTENT',
    'HARM_CATEGORY_HARASSMENT', 'HARM_CATEGORY_SEXUALLY_EXPLICIT')]
TIMEOUT_SEGUNDOS = 15


class ErroProvedor(RuntimeError):
    """Falha HTTP do provedor. Guarda só o status, nunca o corpo nem a URL."""

    def __init__(self, code):
        super().__init__(f'HTTP {code}')
        self.code = code


def validated_text(candidate):
    """Candidato da REST API (dict) -> texto. Não-STOP, ferramenta ou texto vazio/grande: ValueError."""
    if not isinstance(candidate, dict) or candidate.get('finishReason') != 'STOP' or not candidate.get('content'):
        raise ValueError('Provider response not complete')
    parts = candidate['content'].get('parts') or []
    if any('functionCall' in p or 'functionResponse' in p for p in parts):
        raise ValueError('Tools are not authorized')
    text = ''.join(p.get('text') or '' for p in parts if not p.get('thought'))
    if not text or len(text) > 24000:
        raise ValueError('Provider output budget exceeded')
    return text


def transporte_http(modelo, corpo):
    """POST generateContent. Devolve o JSON da resposta. Os testes trocam esta função."""
    chave = obter_api_key()[0]
    if not chave:
        raise RuntimeError('Server credential missing')
    pedido = urllib.request.Request(URL.format(modelo=modelo), data=json.dumps(corpo).encode('utf-8'),
                                    headers={'Content-Type': 'application/json', 'x-goog-api-key': chave})
    try:
        with urllib.request.urlopen(pedido, timeout=TIMEOUT_SEGUNDOS) as resposta:
            return json.loads(resposta.read().decode('utf-8'))
    except urllib.error.HTTPError as erro:
        raise ErroProvedor(erro.code) from None


def corpo_pedido(instruction, texto, schema, max_tokens):
    return {
        'system_instruction': {'parts': [{'text': instruction}]},
        'contents': [{'role': 'user', 'parts': [{'text': texto}]}],
        'safetySettings': SAFETY,
        'generationConfig': {'maxOutputTokens': max_tokens, 'candidateCount': 1,
                             'responseMimeType': 'application/json', 'responseJsonSchema': schema,
                             'thinkingConfig': {'thinkingLevel': 'LOW'}},
    }


def modelo_alternativo(modelo):
    """Próximo modelo homologado diferente de `modelo` (ordem: primeira chamada, contingência, lista Google)."""
    return next((m for m in dict.fromkeys([MODELO_PRIMEIRA_CHAMADA, MODELO_CONTINGENCIA, *MODELOS_GOOGLE])
                 if m != modelo), None)


class GeminiGateway:
    # Tratamento conhecido de 400/404/429/503/504 (desafio_itau/politica/erros_api-v1.json): no máximo UMA nova
    # chamada, sempre com OUTRO modelo homologado. A rota interacao/ desliga isto: o laço de modelos dela já é a
    # nova chamada.
    novas_chamadas = True

    def __init__(self, *, model=MODELO_PRIMEIRA_CHAMADA, guard_model=None, max_calls=60, transporte=None, dormir=None):
        self.model, self.guard_model = model, guard_model or model
        if self.model not in ALLOWED_MODELS or self.guard_model not in ALLOWED_MODELS:
            raise ValueError('Model is not allowlisted')
        self.max_calls, self.calls = max_calls, 0
        self.transporte = transporte or transporte_http
        self.dormir = dormir or asyncio.sleep
        self.metrics = deque(maxlen=300)
        self._lock = threading.Lock()

    def _admit(self):
        with self._lock:
            if self.calls >= self.max_calls:
                raise RuntimeError('Process call budget exhausted')
            self.calls += 1  # Failed/uncertain attempts also count.

    def _metric(self, stage, started, digest, usage=None, model_version=None, outcome='complete', error=None,
                model=None, nova_chamada=False):
        usage = usage or {}
        self.metrics.append({'stage': stage, 'model': model or (self.model if stage == 'generate' else self.guard_model),
                             'model_version': model_version, 'prompt_sha256': digest, 'policy_version': '1.0',
                             'politica_operacional': politica.referencia_documento(),
                             'nova_chamada': nova_chamada,
                             'tratamento_erro': getattr(erros_api.tratamento(erros_api.status_de(error)),
                                                        'acao_servidor', None) if error else None,
                             'latency_ms': round((time.monotonic() - started) * 1000), 'outcome': outcome,
                             'input_tokens': usage.get('promptTokenCount'),
                             'output_tokens': usage.get('candidatesTokenCount'),
                             'total_tokens': usage.get('totalTokenCount'),
                             'error_type': type(error).__name__ if error else None,
                             'http_status': getattr(error, 'code', None) if isinstance(getattr(error, 'code', None), int) else None})

    async def _call(self, stage, model, instruction, digest, data, schema, max_tokens, parse, _nova=False):
        texto = json.dumps(data, ensure_ascii=False)
        if len(texto) > 60000:
            raise ValueError('Context budget exceeded')
        started = time.monotonic()
        try:
            resposta = await asyncio.to_thread(self.transporte, model, corpo_pedido(instruction, texto, schema, max_tokens))
            candidatos = resposta.get('candidates') if isinstance(resposta, dict) else None
            if not candidatos or len(candidatos) != 1:
                raise ValueError('No unique candidate')
            result = parse(validated_text(candidatos[0]))
            self._metric(stage, started, digest, resposta.get('usageMetadata'), resposta.get('modelVersion'),
                         model=model, nova_chamada=_nova)
            return result
        except Exception as error:
            self._metric(stage, started, digest, outcome='failed_or_uncertain', error=error, model=model,
                         nova_chamada=_nova)
            status = erros_api.status_de(error)
            alternativo = modelo_alternativo(model)
            if _nova or not self.novas_chamadas or not alternativo or not erros_api.pode_nova_chamada(status, 0):
                raise
            espera = erros_api.espera_no_servidor(status)
            if espera:
                await self.dormir(espera)
            self._admit()  # a nova chamada também consome o orçamento do processo
            return await self._call(stage, alternativo, instruction, digest, data, schema, max_tokens, parse,
                                    _nova=True)

    async def _guard(self, stage, data, reference_date):
        self._admit()
        instruction, digest = render_prompt(stage, reference_date=reference_date)
        return await self._call(stage, self.guard_model, instruction, digest, data,
                                GuardDecisionV1.model_json_schema(), 512,
                                lambda t: GuardDecisionV1.model_validate_json(t).model_dump())

    async def input_guard(self, message, history):
        return await self._guard('input_guard', {'message': message, 'history': history[-4:]},
                                 datetime.now(timezone.utc).date().isoformat())

    async def output_guard(self, message, draft, context):
        return await self._guard('output_guard', {'question': message, 'draft': draft, 'evidence': context},
                                 context['reference_date'])

    async def generate(self, message, context, history, constraints, titular=None):
        self._admit()
        instruction, digest = render_prompt('system', reference_date=context['reference_date'], titular=titular)
        data = {'message': message, 'context': context, 'history': history, 'constraints': constraints}
        return await self._call('generate', self.model, instruction, digest, data,
                                AgentDraftV1.model_json_schema(), 1800,
                                lambda t: AgentDraftV1.model_validate_json(t).model_dump())
