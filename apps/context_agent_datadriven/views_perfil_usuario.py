"""
Rotas do perfil de usuário ("quem sou eu"). Contrato para o front: docs/contrato-api-frontend.md, seção 5.1.

POST perfil-usuario/definir/   {"usuario": "<id_usuario UUID ou índice>"}  -> 201 {sessao_id, usuario}
POST perfil-usuario/pergunta/  {"sessao_id": "...", "pergunta": "..."}     -> 200 {resposta, usuario, guard}

Erros: 400 corpo inválido · 404 usuário ou sessão inexistente · 502 resposta do modelo reprovada pelo guard ·
503 CSV da verdade ausente (`estado: "NAO_MEDIDO"`) ou nenhum modelo respondeu.
"""

from time import perf_counter

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import perfil_usuario as pu


def _ms(inicio) -> float:
    return round((perf_counter() - inicio) * 1000, 3)


def _executar(funcao, *args, codigo_ok=status.HTTP_200_OK) -> Response:
    inicio = perf_counter()
    try:
        corpo, codigo = funcao(*args), codigo_ok
    except pu.ReferenciaInvalida as erro:
        corpo, codigo = {"erro": str(erro)}, status.HTTP_400_BAD_REQUEST
    except (pu.UsuarioNaoEncontrado, pu.SessaoNaoEncontrada) as erro:
        corpo, codigo = {"erro": str(erro)}, status.HTTP_404_NOT_FOUND
    except pu.RespostaReprovada as erro:
        corpo = {"erro": str(erro), "guard": {"estado": "REPROVADO", "faltam": erro.faltam},
                 "modelo": erro.modelo}
        codigo = status.HTTP_502_BAD_GATEWAY
    except pu.BaseAusente as erro:
        corpo, codigo = {"erro": str(erro), "estado": "NAO_MEDIDO"}, status.HTTP_503_SERVICE_UNAVAILABLE
    except pu.ModeloIndisponivel as erro:
        corpo, codigo = {"erro": str(erro)}, status.HTTP_503_SERVICE_UNAVAILABLE
    return Response({**corpo, "tempo_resposta_ms": _ms(inicio)}, status=codigo)


def _texto(dados, campo, limite):
    valor = dados.get(campo) if isinstance(dados, dict) else None
    if isinstance(valor, int) and not isinstance(valor, bool):
        valor = str(valor)
    if not isinstance(valor, str) or not valor.strip():
        raise pu.ReferenciaInvalida(f"Informe {campo}.")
    if len(valor) > limite:
        raise pu.ReferenciaInvalida(f"{campo} deve ter no máximo {limite} caracteres.")
    return valor.strip()


class PerfilUsuarioDefinirAPI(APIView):
    """Primeira chamada do front: define quem é o usuário e abre a sessão."""

    def post(self, request):
        return _executar(lambda: pu.definir_usuario(_referencia(request.data)),
                         codigo_ok=status.HTTP_201_CREATED)


def _referencia(dados):
    """UUID do usuário, ou "aleatorio" (+ "excluir": UUID atual) para o servidor sortear entre os 1.000 do CSV
    da verdade um id diferente do atual (pedido do front 2026-09-27 14:27: uma chamada em vez de três)."""
    ref = _texto(dados, "usuario", 64)
    if ref.strip().lower() != "aleatorio":
        return ref
    from apps.i_agora.sessao import sortear  # import tardio: i_agora.sessao importa este serviço
    excluir = dados.get("excluir") if isinstance(dados, dict) else None
    return sortear(exclude=str(excluir).strip().lower() if excluir else None)


class PerfilUsuarioPerguntaAPI(APIView):
    """Pergunta do usuário da sessão; o Gemini responde com os fatos do CSV e o guard confere."""

    def post(self, request):
        return _executar(lambda: pu.perguntar(_texto(request.data, "sessao_id", 64),
                                              _texto(request.data, "pergunta", 2000)))
