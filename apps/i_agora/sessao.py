"""Quem é o cliente da sessão do front.

No agent_backend, GET conversas/sessao/ só entregava um cookie e o i-agora/perfil/ sorteava um id_usuario
(tabela `picks`), guardado até o "Testar próximo perfil" (POST sessao/abertura/ {next:true}).
Aqui a sessão já é do perfil_usuario (model SessaoPerfilUsuario, 4 h): o sorteio acontece no GET conversas/sessao/
SEM sessão, cria uma sessão normal de perfil-usuario/definir/ e o titular dela É o cliente do plano. Assim a
conversa (titular) e o plano (client_ref) nunca falam de pessoas diferentes. {next:true} troca o titular da
MESMA sessão por outro id sorteado. O fluxo explícito perfil-usuario/definir/ + ?sessao_id= continua igual.

Sorteio por SITUAÇÃO (dono 2026-09-27 14:39): primeiro a situação financeira (uniforme entre as que têm gente,
fora a da pessoa atual quando há outra), depois um id uniforme dentro dela, sempre != excluir. A situação de cada
id vem de data/situacao_por_usuario.json (scripts/gerar_situacao_por_usuario.py: mesma fonte e mesma regra
domain.situacao_do_mes que a abertura usa). Sem o ficheiro, o sorteio é uniforme e DIZ que é
({"modo": "uniforme", "motivo": "situacao NAO_MEDIDA"}).
"""
import json
import random
import threading
from pathlib import Path

from django.conf import settings

from apps.context_agent_datadriven.services import perfil_usuario

from .domain import SITUACOES

# Sorteio uniforme por sessão (não a "Pessoa 1" fixa para todo visitante). Os testes trocam por um dublê
# com randrange(n).
RNG = random.SystemRandom()

ARQUIVO_SITUACAO = Path(settings.BASE_DIR) / 'data' / 'situacao_por_usuario.json'
NAO_MEDIDO = 'NAO_MEDIDO'
MOTIVO_SEM_SITUACAO = 'situacao NAO_MEDIDA'

_cache = {'chave': None, 'situacao': None}
_trava = threading.Lock()


class SituacaoInvalida(perfil_usuario.ReferenciaInvalida):
    """Categoria pedida em {"situacao": ...} que não existe ou não tem ninguém -> 400 com as válidas."""

    def __init__(self, pedida, validas):
        self.validas = list(validas)
        super().__init__(f'situacao "{pedida}" invalida; validas: {", ".join(self.validas) or "nenhuma"}.')


class SituacaoNaoMedida(perfil_usuario.BaseAusente):
    """Pediram uma situação à força, mas o ficheiro de situações não existe -> 503 NAO_MEDIDO (nunca uniforme
    calado: o pedido era "só dentro desta categoria")."""


def catalogo():
    """id_usuario do CSV da verdade, ordenados."""
    return sorted(perfil_usuario._carregar()['por_uuid'])


def situacoes():
    """{id_usuario: categoria | NAO_MEDIDO} do ficheiro pré-calculado, ou None se ele não existe / não é legível.
    Cache por (caminho, mtime)."""
    caminho = Path(ARQUIVO_SITUACAO)
    try:
        chave = (str(caminho), caminho.stat().st_mtime)
    except OSError:
        return None
    with _trava:
        if _cache['chave'] != chave:
            try:
                dados = json.loads(caminho.read_text(encoding='utf-8'))['situacao']
                _cache['situacao'] = {str(k).lower(): v for k, v in dados.items()}
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                _cache['situacao'] = None
            _cache['chave'] = chave
        return _cache['situacao']


def _escolher(opcoes):
    return opcoes[RNG.randrange(len(opcoes))]


def sortear_com_modo(users=None, exclude=None, situacao=None):
    """-> (id_usuario, sorteio). sorteio = {"modo": "por_situacao", "situacao": cat} ou
    {"modo": "uniforme", "motivo": ...}. O id é sempre != exclude quando o catálogo tem outro."""
    users = catalogo() if users is None else users
    if not users:
        raise perfil_usuario.BaseAusente('Catálogo de clientes vazio.')
    mapa = situacoes()
    if mapa is None:
        if situacao is not None:
            raise SituacaoNaoMedida(f'{MOTIVO_SEM_SITUACAO}: {ARQUIVO_SITUACAO.name} ausente; '
                                    'rode scripts/gerar_situacao_por_usuario.py.')
        return _uniforme(users, exclude, MOTIVO_SEM_SITUACAO)
    grupos = {}
    for u in users:
        cat = mapa.get(u)
        if cat in SITUACOES:  # NAO_MEDIDO (ou ausente do ficheiro) não entra no sorteio por situação
            grupos.setdefault(cat, []).append(u)
    if situacao is not None:
        if situacao not in grupos:
            raise SituacaoInvalida(situacao, [c for c in SITUACOES if c in grupos])
        candidatos = [situacao]
    else:
        # Fora a categoria da pessoa atual, se sobrar outra com alguém que não seja ela.
        atual = mapa.get(exclude) if exclude else None
        candidatos = [c for c in SITUACOES if c in grupos and c != atual and any(u != exclude for u in grupos[c])]
        if not candidatos:
            candidatos = [c for c in SITUACOES if c in grupos and any(u != exclude for u in grupos[c])]
        if not candidatos:
            return _uniforme(users, exclude, MOTIVO_SEM_SITUACAO)
    cat = _escolher(candidatos)
    opcoes = [u for u in grupos[cat] if u != exclude] or list(grupos[cat])
    return _escolher(opcoes), {'modo': 'por_situacao', 'situacao': cat}


def _uniforme(users, exclude, motivo):
    options = [u for u in users if u != exclude] or list(users)
    return _escolher(options), {'modo': 'uniforme', 'motivo': motivo}


def sortear(users=None, exclude=None, situacao=None):
    """id_usuario sorteado por situação (ver sortear_com_modo), diferente de `exclude` sempre que possível."""
    return sortear_com_modo(users, exclude, situacao)[0]


def nova_sessao():
    """Sessão nova com um cliente sorteado -> {sessao_id, usuario, expira_em_segundos} (mesmo formato de definir/)."""
    return perfil_usuario.definir_usuario(sortear())


def trocar_cliente(sessao_id, atual=None):
    """Regra do "próximo perfil": outro id sorteado (por situação, fora a do atual) passa a ser o titular da
    mesma sessão. -> novo id_usuario."""
    novo = sortear(exclude=atual)
    perfil_usuario.trocar_usuario(sessao_id, novo)
    return novo
