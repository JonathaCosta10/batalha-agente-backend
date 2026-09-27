"""Quem é o cliente da sessão do front.

No agent_backend, GET conversas/sessao/ só entregava um cookie e o i-agora/perfil/ sorteava um id_usuario
(tabela `picks`), guardado até o "Testar próximo perfil" (POST sessao/abertura/ {next:true}).
Aqui a sessão já é do perfil_usuario (model SessaoPerfilUsuario, 4 h): o sorteio acontece no GET conversas/sessao/
SEM sessão, cria uma sessão normal de perfil-usuario/definir/ e o titular dela É o cliente do plano. Assim a
conversa (titular) e o plano (client_ref) nunca falam de pessoas diferentes. {next:true} troca o titular da
MESMA sessão por outro id sorteado. O fluxo explícito perfil-usuario/definir/ + ?sessao_id= continua igual.
"""
import random

from apps.context_agent_datadriven.services import perfil_usuario

# Sorteio uniforme por sessão (não a "Pessoa 1" fixa para todo visitante). Os testes trocam por um dublê
# com randrange(n).
RNG = random.SystemRandom()


def catalogo():
    """id_usuario do CSV da verdade, ordenados."""
    return sorted(perfil_usuario._carregar()['por_uuid'])


def sortear(users=None, exclude=None):
    """id_usuario uniforme do catálogo, diferente de `exclude` sempre que o catálogo permitir."""
    users = catalogo() if users is None else users
    if not users:
        raise perfil_usuario.BaseAusente('Catálogo de clientes vazio.')
    options = [u for u in users if u != exclude] or list(users)
    return options[RNG.randrange(len(options))]


def nova_sessao():
    """Sessão nova com um cliente sorteado -> {sessao_id, usuario, expira_em_segundos} (mesmo formato de definir/)."""
    return perfil_usuario.definir_usuario(sortear())


def trocar_cliente(sessao_id, atual=None):
    """Regra do "próximo perfil": outro id sorteado passa a ser o titular da mesma sessão. -> novo id_usuario."""
    novo = sortear(exclude=atual)
    perfil_usuario.trocar_usuario(sessao_id, novo)
    return novo
