"""Metas persistentes, confirmação atômica e concorrência otimista (campo `version`).

Portado de Frontend/agent_backend/planning/store.py (2026-09-27). O SQLite próprio virou models do Django
(models.py). Mesma interface: get/open/prepare_case/withdraw_case/adjust/confirm/progress/reset.
Não portados: pick/repick (o cliente sorteado é o titular da sessão, ver sessao.py) e admit_call (orçamento
diário do provedor; aqui o teto é CONVERSAS['MAX_CHAMADAS'] do gateway).
Limite conhecido: no SQLite o `transaction.atomic` do Django abre a transação DEFERRED (o agent_backend usava
BEGIN IMMEDIATE); duas escritas simultâneas no mesmo plano ainda são recusadas pela checagem de `version`,
mas a segunda pode sair como erro técnico (banco travado) em vez de 409.
"""
import hashlib
import json
from datetime import datetime, timezone

from django.db import transaction

from .domain import from_snapshot, draft_for_case, totals, validate_plan
from .models import ConfirmacaoPlano, PlanoAtivo, PlanoIAgora


class Conflict(ValueError):
    # tipo de erro_api (erros_api-v1.json 1.2.0): plano_desatualizado por padrão; sem_proposta sem caso preparado.
    def __init__(self, mensagem, tipo='plano_desatualizado'):
        super().__init__(mensagem)
        self.tipo = tipo


class PlanStore:
    def _get(self, owner):
        ativo = PlanoAtivo.objects.filter(dono=owner).first()
        if not ativo:
            return None
        linha = PlanoIAgora.objects.filter(dono=owner, ref=ativo.ref).first()
        return json.loads(linha.estado_json) if linha else None

    def _put(self, owner, state):
        state['totals'] = totals(state['confirmed'] or state['draft'])
        PlanoIAgora.objects.update_or_create(dono=owner, ref=str(state['snapshot']['client_ref']),
                                             defaults={'estado_json': json.dumps(state, allow_nan=False)})

    def get(self, owner):
        return self._get(owner)

    def open(self, owner, state):
        ref = str(state['snapshot']['client_ref'])
        with transaction.atomic():
            PlanoAtivo.objects.update_or_create(dono=owner, defaults={'ref': ref})
            existing = self._get(owner)
            if existing:
                return existing
            self._put(owner, state)
            return state

    def prepare_case(self, owner, version, plan_id, case):
        with transaction.atomic():
            s = self._get(owner)
            if not s or s['planId'] != plan_id or s['version'] != version or s['confirmed']:
                raise Conflict('A conversa mudou. Reavalie a proposta no planejamento atual.')
            if case['reference_month'] != s['snapshot']['reference_month']:
                raise ValueError('Referência inválida.')
            s['draft'] = draft_for_case(s['draft'], case)
            s['commitmentCase'] = {**case, 'source': s['snapshot']['seal']['source']}
            s['stage'] = 'confirm'
            s['version'] += 1
            self._put(owner, s)
            return s

    def withdraw_case(self, owner):
        with transaction.atomic():
            s = self._get(owner)
            if s and not s['confirmed'] and (s.get('commitmentCase') or s['stage'] == 'confirm'):
                s.pop('commitmentCase', None)
                s['stage'] = 'invite'
                s['version'] += 1
                self._put(owner, s)
            return s

    def adjust(self, owner, version, changes):
        if set(changes) - {'deliveryTarget', 'shoppingTarget', 'otherCut', 'reserveTarget', 'selected'}:
            raise ValueError('Só metas podem ser ajustadas; não os dados observados.')
        with transaction.atomic():
            s = self._get(owner)
            if not s:
                raise ValueError('Escolha um cliente primeiro.')
            if s['version'] != version:
                raise Conflict('O plano mudou. Recarregue antes de ajustar.')
            if s['confirmed']:
                raise Conflict('Já existe plano confirmado; recomece explicitamente para alterá-lo.')
            s['draft'] = validate_plan({**s['draft'], **changes})
            s['stage'] = 'confirm'
            s['version'] += 1
            self._put(owner, s)
            return s

    def confirm(self, owner, rid, version, plan):
        digest = hashlib.sha256(json.dumps({'version': version, 'plan': plan}, sort_keys=True,
                                           allow_nan=False).encode()).hexdigest()
        with transaction.atomic():
            row = ConfirmacaoPlano.objects.filter(dono=owner, pedido_id=rid).first()
            if row:
                if row.digest != digest:
                    raise Conflict('Identificador já utilizado para outro conteúdo.')
                previous = json.loads(row.resposta_json)
                active = self._get(owner)
                if not active or active['planId'] != previous['state']['planId']:
                    raise Conflict('Este envio pertence a um planejamento encerrado. Confira o plano atual.')
                return {**previous, 'replayed': True}
            s = self._get(owner)
            if not s:
                raise ValueError('Escolha um cliente primeiro.')
            if s['version'] != version:
                raise Conflict('O plano mudou. Confira os dados atuais.')
            if s['confirmed']:
                raise Conflict('Plano já confirmado. Recomece explicitamente para substituí-lo.')
            p = validate_plan(plan)
            if not p['selected']:
                raise ValueError('Selecione pelo menos um compromisso.')
            for key in ('income', 'expenses', 'deliveryCurrent', 'shoppingCurrent', 'period'):
                if p.get(key) != s['draft'].get(key):
                    raise ValueError('A base observada não pode ser modificada na confirmação.')
            t = totals(p)
            if p['otherCut'] > max(0, p['expenses'] - p['deliveryCurrent'] - p['shoppingCurrent']):
                raise ValueError('Outros gastos não podem duplicar as categorias delivery e lojas/sites.')
            if t['released'] > p['expenses']:
                raise ValueError('A redução não pode superar o gasto observado.')
            if t['reserve'] > max(0, t['available']):
                raise ValueError('A reserva proposta supera a disponibilidade deste cenário. Ajuste o plano.')
            s.update(draft=p, confirmed=p, confirmedAt=datetime.now(timezone.utc).isoformat(), stage='card',
                     version=s['version'] + 1)
            self._put(owner, s)
            response = {'state': s, 'replayed': False}
            ConfirmacaoPlano.objects.create(dono=owner, pedido_id=rid, digest=digest, resposta_json=json.dumps(response))
            return response

    def progress(self, owner, version, changes):
        if set(changes) - {'stage', 'phraseIndex'}:
            raise ValueError('Campos não permitidos.')
        with transaction.atomic():
            s = self._get(owner)
            if not s or s['version'] != version:
                raise Conflict('Plano desatualizado.')
            if not s['confirmed']:
                raise ValueError('Confirme o plano antes de avançar.')
            if changes.get('stage', s['stage']) not in ('card', 'finish'):
                raise ValueError('Etapa inválida.')
            if 'phraseIndex' in changes and (type(changes['phraseIndex']) is not int
                                             or not 0 <= changes['phraseIndex'] <= 10000):
                raise ValueError('Frase inválida.')
            s.update(changes)
            s['version'] += 1
            self._put(owner, s)
            return s

    def reset(self, owner):
        with transaction.atomic():
            s = self._get(owner)
            if not s:
                return None
            new = from_snapshot(s['snapshot'])
            new['version'] = s['version'] + 1
            self._put(owner, new)
            return new
