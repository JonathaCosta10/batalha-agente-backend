"""Persistência das conversas de conversas/mensagens/ (Decisão D-4 / I4, 2026-09-27).

Antes, `ConversationService.sessions` vivia só num dict do processo: um reinício do runserver fazia a conversa
responder 404 com a sessão de usuário ainda válida. Agora cada conversa é gravada no banco do Django pelo cache
com backend de banco (django.core.cache.backends.db.DatabaseCache), tabela `conversas_sessao_cache`, criada sob
demanda com a mesma rotina do `manage.py createcachetable` — sem mexer em settings.py nem em migrações.

Mesmo padrão da sessão de perfil-usuario (SessaoPerfilUsuario, migração 0002):
- relógio de PAREDE (time.time), porque time.monotonic() não vale entre dois processos;
- TTL aplicado na LEITURA = perfil_usuario.SESSAO_SEGUNDOS (4 h); o timeout do cache é só um teto de limpeza;
- guarda só o que já ficava em memória: histórico MINIMIZADO (rules.minimize), `criada` e a proposta de
  projeção pendente. Nada de prompt, contexto, instrução ou resposta crua do provedor.
- a chave é sha256(principal|conversation_id) e o valor repete o principal: outro principal não enxerga.
"""
import asyncio
import hashlib
import threading
import time

from apps.context_agent_datadriven.services.perfil_usuario import SESSAO_SEGUNDOS

TABELA = 'conversas_sessao_cache'
VERSAO = 1


# O ConversationService chama o armazém de dentro do laço asyncio (send é async) e o ORM do Django recusa acesso
# síncrono ao banco ali (SynchronousOnlyOperation). Dentro do laço, cada operação corre numa thread própria, que
# fecha a sua conexão ao terminar (sem conexão presa a um banco antigo), e a chamada espera até 10 s.
def _fora_do_laco(fn):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return fn()
    caixa = {}

    def alvo():
        from django.db import connections
        try:
            caixa['valor'] = fn()
        except BaseException as erro:  # devolvido ao chamador, que decide (carregar -> None, gravar -> False)
            caixa['erro'] = erro
        finally:
            connections.close_all()
    linha = threading.Thread(target=alvo, name='conversas-persistencia', daemon=True)
    linha.start()
    linha.join(10)
    if linha.is_alive():
        raise TimeoutError('persistência da conversa: banco não respondeu em 10 s')
    if 'erro' in caixa:
        raise caixa['erro']
    return caixa.get('valor')

def _chave(principal, cid):
    return 'conversa:' + hashlib.sha256(f'{principal}|{cid}'.encode('utf-8')).hexdigest()


class ArmazemConversas:
    """carregar / gravar / apagar uma conversa (principal, conversation_id). Falha do banco nunca derruba a rota:
    `carregar` devolve None e `gravar` devolve False (a conversa segue só em memória, como antes)."""

    def __init__(self, *, ttl=SESSAO_SEGUNDOS, relogio=time.time, database='default'):
        self.ttl, self.relogio, self.database = ttl, relogio, database
        self._cache, self._trava = None, threading.Lock()

    def _backend(self):
        with self._trava:
            if self._cache is None:
                from django.core.cache.backends.db import DatabaseCache
                from django.core.management.commands.createcachetable import Command
                comando = Command()
                comando.verbosity = 0  # handle() é quem define; aqui chamamos create_table direto
                comando.create_table(self.database, TABELA, dry_run=False)
                # Teto de limpeza do próprio cache (tempo real); a regra de expiração é a do TTL na leitura.
                self._cache = DatabaseCache(TABELA, {'TIMEOUT': int(self.ttl) + 60,
                                                     'OPTIONS': {'MAX_ENTRIES': 5000, 'CULL_FREQUENCY': 4}})
            return self._cache

    def carregar(self, principal, cid):
        try:
            valor = _fora_do_laco(lambda: self._backend().get(_chave(principal, cid)))
        except Exception:
            return None
        if not isinstance(valor, dict) or valor.get('versao') != VERSAO or valor.get('principal') != principal \
                or valor.get('cid') != cid:
            return None
        if self.relogio() - valor['criada'] >= self.ttl:
            self.apagar(principal, cid)
            return None
        return valor

    def gravar(self, principal, cid, *, historico, criada, proposta=None):
        valor = {'versao': VERSAO, 'principal': principal, 'cid': cid, 'criada': float(criada),
                 'historico': [{'role': h['role'], 'text': h['text'], **({'falha': True} if h.get('falha') else {})}
                               for h in historico],
                 'proposta': proposta}
        try:
            _fora_do_laco(lambda: self._backend().set(_chave(principal, cid), valor))
            return True
        except Exception:
            return False

    def apagar(self, principal, cid):
        try:
            _fora_do_laco(lambda: self._backend().delete(_chave(principal, cid)))
        except Exception:
            pass
