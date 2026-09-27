"""Bounded local application service. Only release() builds public envelopes.

Portado de agente-app-mobile/agent_backend (commit 1302ba5). Mudanças no backend Django:
- o `principal` é o `sessao_id` de perfil-usuario/definir/ e `send` recebe o `titular` da sessão
  (codigo, pessoa, genero, indice do CSV da verdade);
- o contexto recebe os números reais do titular (context.build_context(titular=...));
- guard de identidade: pergunta "quem sou eu"/nome/código só sai se a resposta trouxer o que
  `perfil_usuario.conferir` exige; senão a resposta é a do CSV, determinística;
- a resposta aprovada leva `dados: {estado, selo}` (campo aditivo ao envelope 1.0).

In-memory store is intentionally single-process/local. Authorization is checked by
Django before EVERY call, including retries. Replace store atomically for production.
"""
import asyncio
import hashlib
import json
import threading
import time
from collections import deque
from copy import deepcopy
from uuid import uuid4
from pydantic import ValidationError
from .schemas import MessageV1, AgentDraftV1, GuardDecisionV1, Claim
from .rules import minimize, safe_text, valid_evidence
from .context import build_context
from . import projection
from .fairness import equality_draft
from . import extremos
from apps.context_agent_datadriven.services.perfil_usuario import SESSAO_SEGUNDOS, classificar, conferir
from desafio_itau import politica
from desafio_itau.politica import erros_api
from . import estado as estado_conversa

FALLBACKS = {
    'auth': 'A conversa requer autenticação e autorização. Entre pelo canal configurado; não envie dados pessoais aqui.',
    'schema': 'Envie uma mensagem de até 2.000 caracteres usando o contrato da conversa, sem campos extras.',
    'not_found': 'Conversa indisponível para esta sessão. Inicie uma nova conversa.',
    'conflict': 'Este identificador já foi usado para outra mensagem. Inicie um novo envio.',
    'limit': 'Limite temporário da conversa atingido. Aguarde antes de tentar novamente.',
    'technical': 'Não consegui validar uma resposta agora. Podemos retomar depois; para organizar o orçamento, comece listando entradas e despesas essenciais, sem enviar identificadores pessoais.',
    'denied': 'Não posso ajudar com acesso a dados de terceiros ou uma finalidade prejudicial. Posso ajudar a formular uma alternativa respeitosa e segura.',
    'clarify': 'Pode explicar o objetivo da pergunta, sem enviar dados de outras pessoas? Assim posso ajudar com a parte segura.',
    'sessao': 'Sessão de usuário não definida ou expirada. Chame POST /api/v1/context-agent/perfil-usuario/definir/ e envie o sessao_id.',
    'demo': 'Demonstração local: esta resposta é fixa, não foi gerada por IA. O i-agora pode apoiar orçamento, reserva e prevenção de dívidas. Nenhum dado bancário foi consultado. Para experimentar respostas do Gemini, o responsável deve habilitar o modo de teste autorizado no servidor.',
}


class ConversationService:
    def __init__(self, gateway=None, *, context_builder=build_context, timeout=45,
                 max_turns=20, max_sessions=100, ttl=None, clock=time.monotonic, requests_per_minute=6,
                 persistencia=None, relogio_parede=time.time):
        # ttl da conversa = vida da sessão de usuário (perfil_usuario.SESSAO_SEGUNDOS, 4 h). Antes: 1800 s fixos,
        # e a conversa morria (404) com a sessão ainda válida (achado D3, 2026-09-27).
        ttl = SESSAO_SEGUNDOS if ttl is None else ttl
        self.gateway, self.context_builder = gateway, context_builder
        self.timeout, self.max_turns, self.max_sessions = timeout, max_turns, max_sessions
        self.ttl, self.clock = ttl, clock
        # I4 / D-4 (2026-09-27): com `persistencia` (persistencia.ArmazemConversas), a conversa sobrevive ao
        # reinício do processo. O relógio da parte persistida é de PAREDE (relogio_parede=time.time): monotonic
        # não vale entre processos. `clock` segue monotonic para o que é só do processo (rate limit, cache).
        self.persistencia, self.relogio_parede = persistencia, relogio_parede
        self.criada_parede = {}
        self.audit = deque(maxlen=1000)  # enums only; no prompts, identifiers or raw exceptions
        self.sessions, self.created, self.cache = {}, {}, {}
        self.proposals = {}
        self.rates, self.requests_per_minute = {}, requests_per_minute
        self.lock, self.em_curso = threading.Lock(), set()

    def release(self, *, code='auth', conversation_id=None, http_status=401,
                draft=None, cached=None, citations=None, permitidos=(), dados=None, encaminhamento=None,
                contrato=None, erro_api=None):
        candidate = cached['reply'] if cached else (draft.reply if draft else FALLBACKS[code])
        if not safe_text(candidate, permitidos):
            cached = draft = dados = contrato = None
            code, http_status, citations = 'technical', 503, []
        self.audit.append({'event': 'release', 'code': code})
        if cached:
            return deepcopy(cached), http_status
        status = {'denied': 'safe_redirect', 'clarify': 'needs_clarification', 'demo': 'ok'}.get(code, 'unavailable')
        body = {
            'schema_version': '1.0', 'conversation_id': conversation_id,
            'message_id': str(uuid4()), 'status': draft.status if draft else status,
            'reply': draft.reply if draft else FALLBACKS[code],
            'citations': citations or [], 'request_id': str(uuid4()),
        }
        if dados is not None:
            body['dados'] = dados
        # Aditivo (contrato publicado pela backend-25 a 2026-09-27 07:30): null ou {destino, motivo, fala_id, ...}
        body['encaminhamento'] = encaminhamento
        # Aditivos (2026-09-27): estado explícito + racional público (estado.py) e tratamento conhecido do erro
        # (erros_api-v1.json: 400/404/429/503/504 -> reformular, reiniciar, aguardar N s ou atendimento humano).
        body['contrato'] = contrato or estado_conversa.contrato(
            estado_conversa.POR_CODIGO.get(code, 'INDISPONIVEL'))
        body['erro_api'] = erro_api or erros_api.erro_api(http_status, 'api')
        return body, http_status

    async def send(self, principal, payload, titular=None):
        if not principal:
            return self.release()
        try:
            request = MessageV1.model_validate(payload)
            if not request.message.strip():
                raise ValueError('empty')
        except (ValidationError, ValueError):
            return self.release(code='schema', http_status=400)
        # Um pedido em curso POR principal (achado D11, 2026-09-27): antes o bloqueio era global e um usuário
        # recebia o 429 do pedido de outro.
        with self.lock:
            if principal in self.em_curso:
                return self.release(code='limit', http_status=429)
            self.em_curso.add(principal)
        try:
            return await self._send(principal, request, titular)
        finally:
            with self.lock:
                self.em_curso.discard(principal)

    def _expire(self):
        for key, created in list(self.created.items()):
            if self.clock() - created >= self.ttl:
                del self.created[key]
                del self.sessions[key]
                self.proposals.pop(key, None)
                self.criada_parede.pop(key, None)
        for key, (_, response, _) in list(self.cache.items()):
            if (key[0], response['conversation_id']) not in self.sessions:
                del self.cache[key]
        for principal, stamps in list(self.rates.items()):
            self.rates[principal] = [s for s in stamps if self.clock() - s < 60]
            if not self.rates[principal]:
                del self.rates[principal]

    async def _send(self, principal, request, titular=None):
        self._expire()
        cid = request.conversation_id
        if cid and (principal, cid) not in self.sessions:
            self._restaurar(principal, cid)
        if cid and (principal, cid) not in self.sessions:
            return self.release(code='not_found', http_status=404)
        key = (principal, cid, request.client_message_id)
        digest = hashlib.sha256(json.dumps(request.model_dump(), sort_keys=True).encode()).hexdigest()
        if key in self.cache:
            previous_digest, response, status = self.cache[key]
            if previous_digest != digest:
                return self.release(code='conflict', http_status=409)
            return self.release(code='cache', cached=response, http_status=status, permitidos=_permitidos(titular))
        if len(self.rates.get(principal, [])) >= self.requests_per_minute:
            return self.release(code='limit', conversation_id=cid, http_status=429)
        if cid is None:
            if len(self.sessions) >= self.max_sessions or sum(p == principal for p, _ in self.sessions) >= 5:
                return self.release(code='limit', http_status=429)
            cid = str(uuid4())
            self.sessions[(principal, cid)] = []
            self.created[(principal, cid)] = self.clock()
            self.criada_parede[(principal, cid)] = self.relogio_parede()
        history = self.sessions[(principal, cid)]
        if len(history) >= self.max_turns * 2:
            return self.release(code='limit', conversation_id=cid, http_status=429)
        message = minimize(request.message)
        stamps = self.rates.setdefault(principal, [])
        stamps.append(self.clock())
        try:
            result = await asyncio.wait_for(self._pipeline(message, history[-12:], cid, (principal, cid), titular), self.timeout)
        except (Exception, asyncio.CancelledError) as error:
            import logging
            logging.getLogger(__name__).warning('conversation_failure type=%s code=%s', type(error).__name__, getattr(error, 'code', None))
            # Cache uncertain outcome. No automatic regeneration/double billing.
            status_erro = erros_api.status_de(error)
            self.audit.append({'event': 'provider_failure', 'http_status': status_erro})
            # O HTTP ao front segue o contrato (503); `erro_api` diz a causa conhecida e o que o cliente pode fazer.
            result = self.release(code='technical', conversation_id=cid, http_status=503,
                                  erro_api=erros_api.erro_api(status_erro, 'provedor'))
        history.extend([{'role': 'user', 'text': message}, {'role': 'model', 'text': result[0]['reply']}])
        self.cache[key] = (digest, deepcopy(result[0]), result[1])
        self._persistir(principal, cid)
        return result

    def _restaurar(self, principal, cid):
        """I4: conversa gravada por outro processo (ou antes do reinício). TTL de parede na leitura; só o mesmo
        principal lê (a chave e o valor carregam o principal)."""
        if self.persistencia is None:
            return
        valor = self.persistencia.carregar(principal, cid)
        if not valor:
            return
        idade = self.relogio_parede() - valor['criada']
        if idade >= self.ttl:
            return
        chave = (principal, cid)
        self.sessions[chave] = [{'role': h['role'], 'text': h['text']} for h in valor['historico']]
        self.created[chave] = self.clock() - idade
        self.criada_parede[chave] = valor['criada']
        if valor.get('proposta'):
            self.proposals[chave] = valor['proposta']
        self.audit.append({'event': 'conversa_restaurada'})

    def _persistir(self, principal, cid):
        if self.persistencia is None:
            return
        chave = (principal, cid)
        if chave not in self.sessions:
            return
        self.persistencia.gravar(principal, cid, historico=self.sessions[chave],
                                 criada=self.criada_parede.setdefault(chave, self.relogio_parede()),
                                 proposta=self.proposals.get(chave))

    async def _pipeline(self, message, history, cid, session_key=None, titular=None):
        # Extremos por REGRA, antes do modelo e do modo demo (extremos.py; contrato da backend-25, 2026-09-27 07:30).
        enc = extremos.detectar(message)
        if enc:
            texto, _fonte = extremos.fala(enc['motivo'])
            self.audit.append({'event': 'encaminhamento', 'motivo': enc['motivo']})
            try:
                extremos.registrar(enc['motivo'], message, 'conversas.mensagens',
                                   indice=(titular or {}).get('indice'))
            except Exception:  # ledger indisponível não impede o encaminhamento
                pass
            draft = AgentDraftV1(reply=texto, status='safe_redirect', capabilities=[], claims=[], missing_data=[])
            return self.release(code='approved', conversation_id=cid, http_status=200, draft=draft,
                                permitidos=_permitidos(titular), encaminhamento=enc,
                                contrato=estado_conversa.contrato('ENCAMINHAMENTO', draft=draft))
        if self.gateway is None:
            return self.release(code='demo', conversation_id=cid, http_status=200)
        pending = self.proposals.pop(session_key, None)
        decision = GuardDecisionV1.model_validate(await self.gateway.input_guard(message, history))
        self.audit.append({'event': 'input_guard', 'decision': decision.decision})
        counter_speech = equality_draft(message, {'sources': []})
        intencao = classificar(message) if titular else 'livre'
        # A pergunta do titular sobre a própria identidade é segura: a resposta de reserva sai do CSV.
        propria = intencao != 'livre' and 'privacy' not in decision.reason_codes
        if decision.decision == 'deny' and not propria and (counter_speech is None or 'privacy' in decision.reason_codes):
            return self.release(code='denied', conversation_id=cid, http_status=200)
        if decision.decision == 'clarify' and not propria and counter_speech is None:
            return self.release(code='clarify', conversation_id=cid, http_status=200)
        if decision.decision not in ('allow', 'constrain', 'deny', 'clarify'):
            raise ValueError('Invalid input decision')
        context = self.context_builder(titular=titular)
        counter_speech = equality_draft(message, context) if counter_speech else None
        context['user_reported_history'] = deepcopy(history)
        next_proposal = None
        rota = 'rascunho'
        if counter_speech is not None:
            draft = counter_speech
        elif pending and projection.is_confirmation(message):
            rota = 'simulacao'
            result = projection.project(pending['current_spending'], pending['target_spending'])
            self.audit.append({'event': 'projection_calculated'})
            calculated = {**pending, **result}
            context['facts'].extend({'id':'PROJECTION:'+k, 'value':str(v), 'origin':'deterministic_confirmed_projection'}
                                    for k,v in calculated.items() if v is not None)
            context['projection'] = {'inputs_confirmed_by_user':pending, 'calculated':result,
                'rates_are_hypotheses':True,
                'rates':{k:str(politica.parametro('projecao.hipoteses_reducao',k)) for k in ('r_5','r_8')},'formula':'G(n)=G_atual*(1-r)^n',
                'currency':'BRL','periodicity':'monthly','commitment_saved':False}
            draft = AgentDraftV1(reply=projection.explain(pending,result), status='ok', capabilities=['orcamento'],
                claims=[Claim(kind='financial',evidence_id='PROJECTION:'+k,text=k,value=str(v))
                        for k,v in calculated.items() if v is not None and k in ('current_spending','target_spending','reference_month','n_5','n_8')], missing_data=[])
        elif propria and decision.decision in ('deny', 'clarify'):
            draft = identity_draft(titular)
            rota = 'identidade'
            self.audit.append({'event': 'identity_guard', 'estado': 'CSV'})
        else:
            draft = AgentDraftV1.model_validate(await self.gateway.generate(
                message, context, history, decision.constraints, titular=titular))
            if intencao != 'livre':
                faltam = conferir(draft.reply, titular, intencao)
                self.audit.append({'event': 'identity_guard', 'estado': 'REPROVADO' if faltam else 'APROVADO'})
                rota = 'identidade'
                if faltam:
                    draft = identity_draft(titular)
            if draft.projection_proposal:
                try:
                    reported = [h['text'] for h in history if h['role']=='user'] + [message]
                    next_proposal = projection.validate_proposal(draft.projection_proposal.model_dump(), reported)
                except ValueError:
                    draft = AgentDraftV1(reply='Para projetar com segurança, preciso dos valores mensais comparáveis e do mês de referência, sem inventar dados. Qual informação você quer corrigir ou completar?',
                        status='needs_clarification',capabilities=['orcamento'],claims=[],missing_data=['projection_inputs'])
                else:
                    context['projection'] = {'proposal_reported_by_user':next_proposal,'awaiting_confirmation':True}
                    context['facts'].extend({'id':'PROPOSAL:'+k,'value':v,'origin':'user_reported_unconfirmed'} for k,v in next_proposal.items())
                    draft = AgentDraftV1(reply=projection.confirmation(next_proposal),status='needs_clarification',capabilities=['orcamento'],claims=[],missing_data=['confirmation'])
                    rota = 'confirmacao_projecao'
        # Validações determinísticas ANTES do output_guard: texto (sensível + léxico contextual), evidências,
        # números sem fonte (a redação não acrescenta valores) e transição de estado permitida.
        sem_fonte = estado_conversa.numeros_sem_fonte(draft.reply, context)
        try:
            estado = estado_conversa.decidir(rota, dados_estado=(context.get('dados_usuario') or {}).get('estado'),
                                             draft=draft, context=context)
        except estado_conversa.TransicaoInvalida:
            estado = None
        if not safe_text(draft.reply, _permitidos(titular)) or not valid_evidence(draft, context) \
                or sem_fonte or estado is None:
            self.audit.append({'event': 'deterministic_reject', 'numeros_sem_fonte': len(sem_fonte),
                               'transicao_invalida': estado is None})
            return self.release(code='technical', conversation_id=cid, http_status=503)
        check = GuardDecisionV1.model_validate(await self.gateway.output_guard(message, draft.model_dump(), context))
        self.audit.append({'event': 'output_guard', 'decision': check.decision, 'reason_codes': check.reason_codes})
        if check.decision != 'release':
            import logging
            logging.getLogger(__name__).warning('output_guard_replaced reasons=%s', check.reason_codes)
            return self.release(code='technical', conversation_id=cid, http_status=503)
        if next_proposal is not None:
            self.proposals[session_key] = next_proposal
        sources = {s['id']: s for s in context['sources']}
        citations = [dict(id=i, url=sources[i]['url'], excerpt=sources[i]['text'],
                          limitations=sources[i]['limitations'], status=sources[i]['status'])
                     for i in dict.fromkeys(c.evidence_id for c in draft.claims) if i in sources]
        dados = context.get('dados_usuario')
        extra = (politica.referencia('projecao.hipoteses_reducao'),) if estado == 'SIMULACAO' else ()
        return self.release(code='approved', conversation_id=cid, http_status=200, draft=draft, citations=citations,
                            permitidos=_permitidos(titular),
                            contrato=estado_conversa.contrato(estado, draft=draft, context=context, extra_regras=extra),
                            dados={'estado': dados['estado'], 'selo': dados.get('selo')} if titular and dados else None)


def _permitidos(titular):
    return (titular['codigo'],) if titular else ()


def identity_draft(titular):
    """Resposta de identidade com os fatos do CSV da verdade, sem modelo."""
    # Regra do dono (2026-09-27 10:22): nome gerado do mesmo id vale; gênero nunca sai (sem "identificada/o").
    return AgentDraftV1(
        reply=(f"Você é {titular['pessoa']}, com o código {titular['codigo']} nesta sessão. "
               'Esses dados vêm do cadastro de demonstração do protótipo, não de um cadastro bancário.'),
        status='ok', capabilities=[], claims=[], missing_data=[])
