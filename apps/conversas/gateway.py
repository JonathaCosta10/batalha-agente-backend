"""Gemini no servidor: dois guards + um gerador, por HTTP (sem google-genai/ADK).

Portado de agente-app-mobile/agent_backend/conversation/gateway.py (commit 1302ba5). O original usa o
SDK google.genai e o Runner do ADK; aqui a chamada é a mesma REST `generateContent` que o backend já usa
em `agentes/LLM_Models/google/cliente.py`, com chave de `desafio_itau.segredos.obter_api_key()` e nomes
de modelo de `desafio_itau.modelos_llm`. Mantém do original: saída JSON com schema, sem ferramentas, sem
retry do provedor, candidato único terminado em STOP, orçamento de chamadas por processo, métricas sem
conteúdo nem chave. A chave vai no header `x-goog-api-key`, nunca na URL.
"""
import asyncio
import contextvars
import inspect
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
TIMEOUT_SEGUNDOS = 15  # etapa sem entrada em TIMEOUT_POR_ETAPA
# Timeout por etapa (2026-09-27, backend-22). Medido: guards bem-sucedidos 906-2235 ms (conversas, 11:44 e 12:26 BRT)
# e 34 chamadas gemini-3.5-flash-lite da rota interacao/ com p50 1250 / p95 1516 / máx 1812 ms (ledger
# relatorios/avaliacoes/2026-09-27.jsonl); falhas por timeout: gemini-3.5-flash parado 15109-15188 ms (3/3, 12:26-12:28
# BRT). Guard a 10 s = 4,5x o máximo medido; o generate fica em 15 s (nenhuma amostra de sucesso acima de 2 s justifica
# subir). Caminho feliz no pior caso: 10 + 15 + 10 = 35 s < 45 s (ConversationService.timeout) < 50 s (front).
TIMEOUT_POR_ETAPA = {'input_guard': 10, 'output_guard': 10, 'generate': 15}
# Timeout ADAPTATIVO com o router e prazo do turno (1.4.0, 503 real do dono às 13:35 com 18 s livres): cada tentativa
# usa min(teto da etapa, prazo restante - reserva para as etapas seguintes). Medido 2026-09-27 com o contexto depois da
# abertura (8-9 mil tokens): gemini-3.1-flash-lite generate 2,7-14,9 s, output_guard >10 s em 3/4 (timeouts de 10 s);
# gemini-3.6-flash output_guard 1,6-1,8 s. Reserva depois do input_guard = generate (10) + output_guard (6) + resposta
# (2); depois do generate = output_guard (6) + resposta (2); depois do output_guard = resposta (2).
# Sem prazo (testes, rota interacao/) vale TIMEOUT_POR_ETAPA.
TETO_ADAPTATIVO_S = {'input_guard': 10, 'generate': 20, 'output_guard': 20}
RESERVA_APOS_S = {'input_guard': 18, 'generate': 8, 'output_guard': 2}
MIN_TENTATIVA_S = 3  # abaixo disto não se começa uma chamada (o guard mais rápido medido levou 0,9 s; generate 2,7 s)


def motivo_do_erro(error):
    """Motivo (vocabulário do router) do erro de UMA tentativa; coerente com o status que define o tipo do front."""
    if isinstance(error, RespostaInvalida):
        return 'resposta_invalida'
    status = erros_api.status_de(error)
    if status == 429:
        return 'cota_dia' if getattr(error, 'cota', None) == 'dia' else 'cota_minuto'
    return {504: 'timeout', 404: 'nao_encontrado'}.get(status) or \
        ('indisponivel' if isinstance(status, int) and status >= 500 else None)


def timeout_da_tentativa(stage, agora=None, teto=None):
    """Segundos para a próxima tentativa da etapa; pode vir < MIN_TENTATIVA_S (quem chama decide não tentar).
    `teto`: `capacidades.<modelo>.timeout_s.<etapa>` (cotas-gemini 1.1.0); None = TETO_ADAPTATIVO_S."""
    prazo = PRAZO_TURNO.get()
    if prazo is None:
        return TIMEOUT_POR_ETAPA.get(stage, TIMEOUT_SEGUNDOS)
    agora = time.monotonic() if agora is None else agora
    disponivel = prazo - agora - RESERVA_APOS_S.get(stage, 2)
    return min(teto or TETO_ADAPTATIVO_S.get(stage, TIMEOUT_SEGUNDOS), disponivel)
# 429 com quotaId "...PerDay..." (cota DIÁRIA do modelo esgotada, medido 2026-09-27 12:29 BRT nos três modelos
# homologados): o modelo fica fora por esta pausa, sem chamada ao provedor; depois UMA chamada real volta a sondar.
# Não muda a política (erros_api-v1.json): nenhum pedido é repetido e continua no máximo uma nova chamada.
PAUSA_COTA_DIARIA_S = 900


class ErroProvedor(RuntimeError):
    """Falha HTTP do provedor. Guarda só o status e, no 429, o tipo de cota ('dia'/'minuto'); nunca o corpo nem a URL."""

    def __init__(self, code, cota=None, retry_s=None):
        super().__init__(f'HTTP {code}')
        self.code = code
        self.cota = cota
        self.retry_s = retry_s


def detalhes_429(corpo):
    """Corpo JSON do 429 do Gemini -> (cota 'dia'|'minuto'|None, retryDelay em s|None). Lê só `quotaId` e
    `retryDelay` de `details[]`; nenhum texto livre."""
    try:
        detalhes = json.loads(corpo).get('error', {}).get('details', [])
        detalhes = [d for d in detalhes if isinstance(d, dict)]
        ids = [v.get('quotaId') or '' for d in detalhes for v in (d.get('violations') or []) if isinstance(v, dict)]
        atraso = next((d.get('retryDelay') for d in detalhes if isinstance(d.get('retryDelay'), str)), None)
    except (ValueError, AttributeError, TypeError):
        return None, None
    retry_s = None
    if atraso and atraso.endswith('s'):
        try:
            retry_s = max(1, min(3600, round(float(atraso[:-1]))))
        except ValueError:
            retry_s = None
    cota = 'dia' if any('PerDay' in i for i in ids) else 'minuto' if any('PerMinute' in i for i in ids) else None
    return cota, retry_s


def cota_do_429(corpo):
    """Corpo JSON do 429 do Gemini -> 'dia' | 'minuto' | None. Lê só `details[].violations[].quotaId`."""
    return detalhes_429(corpo)[0]


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


# Teto de saída por etapa. `maxOutputTokens` do Gemini INCLUI os tokens de pensamento: medido 2026-09-27 13:15 BRT no
# gemini-3.1-flash-lite, output_guard com 490 de pensamento no teto antigo de 512 -> finishReason MAX_TOKENS e JSON
# cortado em '{"decision": "release",'; generate com 1026 de pensamento + 260 de texto (teto antigo 1800). O texto
# útil continua limitado por `validated_text` (24000 caracteres) e pelos schemas.
MAX_TOKENS_GUARD = 2048
MAX_TOKENS_GENERATE = 4096
# Prazo do turno (monotonic) posto pelo ConversationService antes do wait_for de 45 s: o router só começa uma nova
# tentativa se ela couber inteira (timeout da etapa) antes do prazo. Sem prazo (testes, interacao/): sem esse corte.
PRAZO_TURNO = contextvars.ContextVar('prazo_turno', default=None)


class RespostaInvalida(ValueError):
    """O modelo respondeu (HTTP 200), mas a saída não serve: não-STOP (ex.: MAX_TOKENS), JSON inválido ou fora do
    schema estrito. Não é erro do nosso pedido (400) nem do provedor fora (5xx): o router tenta o próximo modelo."""

    def __init__(self, motivo):
        super().__init__(f'Invalid model output: {motivo}')
        self.motivo = motivo


def _resultado(erro, status):
    """Rótulo curto da tentativa para GET conversas/status/ (só números e nomes, nada do texto)."""
    if isinstance(erro, RespostaInvalida):
        return f'resposta_invalida:{erro.motivo}'
    if status == 429:
        return f'429:{getattr(erro, "cota", None) or "sem_tipo"}'
    return str(status) if status is not None else type(erro).__name__


def decisao_guard(texto):
    """Texto do guard -> GuardDecisionV1. `policy_version` é do servidor, não do modelo: medido 2026-09-27 12:58 BRT,
    o gemini-3.1-flash-lite ignora o `const` do schema e escreve a data ('2026-09-27'), o que reprovava 4/4 guards.
    Só esse campo é carimbado; decision/reason_codes/constraints continuam validados sem folga (extra proibido)."""
    bruto = json.loads(texto)
    if not isinstance(bruto, dict):
        raise ValueError('Guard output is not an object')
    bruto['policy_version'] = '1.0'
    return GuardDecisionV1.model_validate_json(json.dumps(bruto)).model_dump()


def transporte_http(modelo, corpo, timeout=TIMEOUT_SEGUNDOS):
    """POST generateContent. Devolve o JSON da resposta. Os testes trocam esta função."""
    chave = obter_api_key()[0]
    if not chave:
        raise RuntimeError('Server credential missing')
    pedido = urllib.request.Request(URL.format(modelo=modelo), data=json.dumps(corpo).encode('utf-8'),
                                    headers={'Content-Type': 'application/json', 'x-goog-api-key': chave})
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
            return json.loads(resposta.read().decode('utf-8'))
    except urllib.error.HTTPError as erro:
        cota = retry_s = None
        if erro.code == 429:
            try:
                cota, retry_s = detalhes_429(erro.read()[:20000])
            except Exception:  # corpo ilegível: segue 429 sem tipo de cota
                cota = retry_s = None
        raise ErroProvedor(erro.code, cota, retry_s) from None


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

    def __init__(self, *, model=MODELO_PRIMEIRA_CHAMADA, guard_model=None, max_calls=60, transporte=None, dormir=None,
                 relogio=time.monotonic, roteador=None):
        self.model, self.guard_model = model, guard_model or model
        if self.model not in ALLOWED_MODELS or self.guard_model not in ALLOWED_MODELS:
            raise ValueError('Model is not allowlisted')
        # Router por etapa/erro (roteador.py + cotas-gemini-v1.json). Sem ele, o comportamento anterior (um modelo por
        # etapa + modelo_alternativo) fica igual — a rota interacao/ e os testes antigos usam esse caminho.
        self.roteador = roteador
        self.max_calls, self.calls = max_calls, 0
        self.transporte = transporte or transporte_http
        # Transporte que aceita `timeout` recebe o da etapa (TIMEOUT_POR_ETAPA); dublês de 2 argumentos seguem iguais.
        try:
            self._com_timeout = 'timeout' in inspect.signature(self.transporte).parameters
        except (TypeError, ValueError):
            self._com_timeout = False
        self.dormir = dormir or asyncio.sleep
        self.relogio = relogio
        self.cota_esgotada = {}  # modelo -> instante (relogio) até quando fica fora por cota diária (429 PerDay)
        self.metrics = deque(maxlen=300)
        self._lock = threading.Lock()

    def cota_diaria_esgotada(self):
        """{modelo: segundos até a nova sonda} dos modelos fora por 429 de cota diária. Só modelo e número."""
        if self.roteador is not None:
            return {m: r['restam_s'] for m, r in self.roteador.estado()['resfriamentos'].items()
                    if r['motivo'] == 'cota_dia'}
        agora = self.relogio()
        return {m: round(ate - agora) for m, ate in list(self.cota_esgotada.items()) if ate > agora}

    async def _uma_chamada(self, stage, model, instruction, digest, texto, schema, max_tokens, parse, nova,
                           timeout=None):
        """Uma chamada real ao provedor (router): métrica, RPM do processo e resfriamento do modelo que falhou.
        `timeout`: segundos desta tentativa (adaptativo, `timeout_da_tentativa`); None = TIMEOUT_POR_ETAPA."""
        started = time.monotonic()
        self.roteador.chamou(model)
        resposta = None
        try:
            if timeout is None:
                timeout = TIMEOUT_POR_ETAPA.get(stage, TIMEOUT_SEGUNDOS)
            corpo = corpo_pedido(instruction, texto, schema, max_tokens)
            resposta = await (asyncio.to_thread(self.transporte, model, corpo, timeout=timeout) if self._com_timeout
                              else asyncio.to_thread(self.transporte, model, corpo))
            candidatos = resposta.get('candidates') if isinstance(resposta, dict) else None
            try:
                if not candidatos or len(candidatos) != 1:
                    raise ValueError('No unique candidate')
                final = candidatos[0].get('finishReason') if isinstance(candidatos[0], dict) else None
                if final and final != 'STOP':
                    raise RespostaInvalida(final)  # ex.: MAX_TOKENS (JSON cortado), SAFETY
                result = parse(validated_text(candidatos[0]))
            except RespostaInvalida:
                raise
            except ValueError as invalida:  # JSON inválido, schema (pydantic ValidationError), texto vazio/grande
                raise RespostaInvalida(type(invalida).__name__) from invalida
        except Exception as error:
            status = erros_api.status_de(error)
            self.roteador.falhou(model, status, getattr(error, 'cota', None), getattr(error, 'retry_s', None))
            self.roteador.tentou(stage, model, _resultado(error, status))
            usage = resposta.get('usageMetadata') if isinstance(resposta, dict) else None
            versao = resposta.get('modelVersion') if isinstance(resposta, dict) else None
            self._metric(stage, started, digest, usage, versao, outcome='failed_or_uncertain', error=error,
                         model=model, nova_chamada=nova)
            raise
        self.roteador.respondeu(stage, model)
        self.roteador.tentou(stage, model, 'ok')
        self._metric(stage, started, digest, resposta.get('usageMetadata'), resposta.get('modelVersion'),
                     model=model, nova_chamada=nova)
        return result

    async def _call_roteado(self, stage, instruction, digest, data, schema, max_tokens, parse):
        """Router: primeiro modelo disponível da etapa, e depois de cada falha o próximo escolhido pelos dados
        (429/503/404 -> próximo da ordem com cota; 504 -> o mais rápido; 400 -> não troca).

        - Erro do provedor com nova chamada admitida pela política (503/5xx, 504 timeout, 429, 404): com
          `limites.troca_de_modelo_no_turno == 'ordem_no_prazo'` (erros_api 1.4.0, pedido do dono 12:39) segue para o
          PRÓXIMO modelo ainda não tentado da ordem da etapa, quantas vezes couber no prazo do turno; com 'uma' vale o
          antigo `novas_chamadas_max` (1). O MESMO modelo nunca é chamado duas vezes na etapa (`excluir=tentados`).
        - 400 (`resposta_segura`) e erro sem status não trocam: sai o erro.
        - Resposta inválida do modelo (HTTP 200 sem saída válida, `RespostaInvalida`) e 429 de cota DIÁRIA também
          seguem para o próximo modelo não tentado (nunca contaram como nova chamada).
        - Timeout ADAPTATIVO: cada tentativa usa `timeout_da_tentativa(stage)` = min(teto da etapa, prazo restante -
          reserva das etapas seguintes). Uma troca só começa se sobrarem >= MIN_TENTATIVA_S; senão sai o erro da
          última tentativa (o front recebe o tipo dele: 504 timeout_provedor, 503 provedor_indisponivel...).
        - Modelo em resfriamento é pulado sem chamada."""
        texto = json.dumps(data, ensure_ascii=False)
        if len(texto) > 60000:
            raise ValueError('Context budget exceeded')
        modelo = self.roteador.escolher(stage)
        if modelo is None:
            # Todos em resfriamento/teto de RPM: nenhuma chamada; o front recebe o tipo do bloqueio (cota -> 429).
            with self._lock:
                self.calls -= 1
            status = self.roteador.motivo_sem_modelo(stage)
            self.roteador.tentou(stage, 'nenhum', 'sem_modelo_disponivel')
            self._metric(stage, time.monotonic(), digest, outcome='sem_modelo_disponivel',
                         error=ErroProvedor(status), model='nenhum')
            erro = ErroProvedor(status, 'resfriamento')
            self._anota_bloqueio(stage, erro)
            raise erro
        try:
            return await self._tentar_ordem(stage, modelo, instruction, digest, texto, schema, max_tokens, parse)
        except Exception as error:
            self._anota_bloqueio(stage, error)
            raise

    def _anota_bloqueio(self, stage, error):
        """Espera REAL até o próximo modelo da etapa ficar livre e o motivo (cotas 1.1.0, dono 14:09): o serviço põe no
        erro_api.tentar_novamente_em_s / Retry-After em vez do fixo da política; 'cota_dia' quando todos estão sem cota
        do dia."""
        try:
            error.espera_restante_s = self.roteador.espera_restante(stage)
            if getattr(error, 'cota', None) == 'resfriamento':
                # nenhuma chamada: o motivo é o do bloqueio que deu o status (429 -> cota_*/rpm, nunca 'timeout')
                error.motivo_bloqueio = self.roteador.motivo_bloqueio(stage, status=getattr(error, 'code', None))
            else:
                error.motivo_bloqueio = motivo_do_erro(error)  # o da ÚLTIMA tentativa, que define o tipo
        except AttributeError:
            pass

    def _max_tokens(self, modelo, stage, padrao):
        return self.roteador.max_output_tokens(modelo, 'generate' if stage == 'generate' else 'guard') or padrao

    async def _tentar_ordem(self, stage, modelo, instruction, digest, texto, schema, max_tokens, parse):
        em_ordem = erros_api.carregar().limites.troca_de_modelo_no_turno == 'ordem_no_prazo'
        tentados, novas_http, nova = set(), 0, False
        # a 1ª tentativa sempre sai (o wait_for do turno é o teto); teto por modelo vem de capacidades.timeout_s
        timeout = max(1.0, timeout_da_tentativa(stage, teto=self.roteador.teto_tentativa(modelo, stage)))
        while True:
            try:
                return await self._uma_chamada(stage, modelo, instruction, digest, texto, schema,
                                               self._max_tokens(modelo, stage, max_tokens), parse, nova, timeout)
            except Exception as error:
                tentados.add(modelo)
                status = erros_api.status_de(error)
                if not self.novas_chamadas:
                    raise
                # 429 de cota DIÁRIA: o provedor recusou sem processar (medido 360-515 ms). É a mesma informação do
                # resfriamento — que é pulado sem contar — só que descoberta numa chamada (processo recém-iniciado).
                # Não gasta a nova chamada da política (visto na :8013 13:20: timeout -> 3.5-flash-lite 429 dia -> fim).
                sem_cota_do_dia = status == 429 and getattr(error, 'cota', None) == 'dia'
                if not isinstance(error, RespostaInvalida) and not sem_cota_do_dia:
                    if em_ordem:
                        if not erros_api.pode_nova_chamada(status, 0):
                            raise  # 400 / sem status: a política não admite outra chamada
                    else:
                        if not erros_api.pode_nova_chamada(status, novas_http):
                            raise
                        novas_http += 1
                proximo = self.roteador.escolher(stage, excluir=tentados, status=status)
                if proximo is None:
                    raise
                espera = erros_api.espera_no_servidor(status)
                timeout = timeout_da_tentativa(stage, time.monotonic() + espera,
                                               teto=self.roteador.teto_tentativa(proximo, stage))
                if timeout < MIN_TENTATIVA_S:
                    raise  # a próxima tentativa não cabe no prazo do turno: sai o erro desta
                if espera:
                    await self.dormir(espera)
                self._admit()  # a nova chamada também consome o orçamento do processo
                modelo, nova = proximo, True

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
                             'motivo_invalida': getattr(error, 'motivo', None),
                             'http_status': getattr(error, 'code', None) if isinstance(getattr(error, 'code', None), int) else None})

    async def _call(self, stage, model, instruction, digest, data, schema, max_tokens, parse, _nova=False):
        if self.roteador is not None and stage in TIMEOUT_POR_ETAPA:
            return await self._call_roteado(stage, instruction, digest, data, schema, max_tokens, parse)
        texto = json.dumps(data, ensure_ascii=False)
        if len(texto) > 60000:
            raise ValueError('Context budget exceeded')
        started = time.monotonic()
        try:
            if self.cota_esgotada.get(model, 0) > self.relogio():
                # Cota DIÁRIA deste modelo esgotada (429 PerDay medido há menos de PAUSA_COTA_DIARIA_S): não gasta
                # chamada nem latência; segue o tratamento do 429 (outro modelo, no máximo uma nova chamada).
                with self._lock:
                    self.calls -= 1  # não houve chamada ao provedor: devolve a unidade do orçamento
                raise ErroProvedor(429, 'dia_pausa')
            timeout = TIMEOUT_POR_ETAPA.get(stage, TIMEOUT_SEGUNDOS)
            corpo = corpo_pedido(instruction, texto, schema, max_tokens)
            resposta = await (asyncio.to_thread(self.transporte, model, corpo, timeout=timeout) if self._com_timeout
                              else asyncio.to_thread(self.transporte, model, corpo))
            candidatos = resposta.get('candidates') if isinstance(resposta, dict) else None
            if not candidatos or len(candidatos) != 1:
                raise ValueError('No unique candidate')
            result = parse(validated_text(candidatos[0]))
            self._metric(stage, started, digest, resposta.get('usageMetadata'), resposta.get('modelVersion'),
                         model=model, nova_chamada=_nova)
            return result
        except Exception as error:
            pausado = getattr(error, 'cota', None) == 'dia_pausa'
            if getattr(error, 'cota', None) == 'dia':
                self.cota_esgotada[model] = self.relogio() + PAUSA_COTA_DIARIA_S
            self._metric(stage, started, digest, outcome='pulado_cota_diaria' if pausado else 'failed_or_uncertain',
                         error=error, model=model, nova_chamada=_nova)
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
                                GuardDecisionV1.model_json_schema(), MAX_TOKENS_GUARD, decisao_guard)

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
                                AgentDraftV1.model_json_schema(), MAX_TOKENS_GENERATE,
                                lambda t: AgentDraftV1.model_validate_json(t).model_dump())
