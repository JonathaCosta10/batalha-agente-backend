"""
Rotas do usuário real (BigQuery, ADC). Contrato para o front: docs/contrato-api-frontend.md.

Erros seguem o padrão do projeto, {"erro": ...} com `tempo_resposta_ms`:
400 referência/data inválida · 404 usuário inexistente · 422 tópico/categoria/pergunta fora do catálogo ·
503 fonte OFF (`estado: "OFF"`) ou BigQuery indisponível (`estado: "NAO_MEDIDO"`).
"""

from time import perf_counter

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .pastas_raiz.estudos.i_agora.visoes import ForaDoCatalogo
from .services import usuario_real

VALORES_SIM = {"1", "true", "sim"}


def _ms(inicio) -> float:
    return round((perf_counter() - inicio) * 1000, 3)


def _executar(funcao, *args, **kwargs) -> Response:
    inicio = perf_counter()
    try:
        corpo, codigo = funcao(*args, **kwargs), status.HTTP_200_OK
    except usuario_real.UsuarioRealDesligado as erro:
        corpo, codigo = {"erro": str(erro), "estado": "OFF"}, status.HTTP_503_SERVICE_UNAVAILABLE
    except usuario_real.FonteIndisponivel as erro:
        corpo, codigo = {"erro": str(erro), "estado": "NAO_MEDIDO"}, status.HTTP_503_SERVICE_UNAVAILABLE
    except usuario_real.ReferenciaInvalida as erro:
        corpo, codigo = {"erro": str(erro)}, status.HTTP_400_BAD_REQUEST
    except usuario_real.UsuarioNaoEncontrado as erro:
        corpo, codigo = {"erro": str(erro)}, status.HTTP_404_NOT_FOUND
    except ForaDoCatalogo as erro:
        corpo, codigo = {"erro": str(erro)}, status.HTTP_422_UNPROCESSABLE_ENTITY
    return Response({**corpo, "tempo_resposta_ms": _ms(inicio)}, status=codigo)


class UsuarioRealStatusAPI(APIView):
    """GET status/ — ON/OFF sem rede; ?validar=1 faz a consulta da lista e informa VALIDADA/FALHOU."""

    def get(self, request):
        validar = str(request.GET.get("validar", "")).strip().lower() in VALORES_SIM
        return _executar(usuario_real.estado, validar=validar)


class UsuarioRealListaAPI(APIView):
    """GET usuario-real/?limite=20&offset=0 — página da lista ordenada por id_usuario."""

    def get(self, request):
        def pagina():
            try:
                limite = min(max(int(request.GET.get("limite", 20)), 1), 1000)
                offset = max(int(request.GET.get("offset", 0)), 0)
            except ValueError as erro:
                raise usuario_real.ReferenciaInvalida("limite e offset devem ser inteiros.") from erro
            lista = usuario_real.listar_usuarios()
            return {"total": lista["total"], "limite": limite, "offset": offset,
                    "usuarios": lista["usuarios"][offset:offset + limite], "selo": lista["selo"]}
        return _executar(pagina)


class UsuarioRealPerfilAPI(APIView):
    """GET usuario-real/<ref>/ — usuário, resumo T3 e as cinco visões."""

    def get(self, request, referencia):
        return _executar(usuario_real.perfil, referencia, data_corte=request.GET.get("data_corte"))


class UsuarioRealVisaoAPI(APIView):
    """GET usuario-real/<ref>/visao/<topico>/?categoria=Delivery — uma visão do catálogo."""

    def get(self, request, referencia, topico):
        return _executar(usuario_real.visao, referencia, topico,
                         categoria=request.GET.get("categoria"), data_corte=request.GET.get("data_corte"))


class UsuarioRealSaldoMesAPI(APIView):
    """GET usuario-real/<ref>/saldo-mes/[?data_corte=] — entradas, saídas e saldo do dia 1 do mês até o corte."""

    def get(self, request, referencia):
        return _executar(usuario_real.saldo_mes, referencia, data_corte=request.GET.get("data_corte"))


class PlanoPropostaAPI(APIView):
    """POST i-agora/plano/proposta/ {"ref": 928 | "<uuid>", "data_corte"?} — compromissos pela modelagem.
    GET com ?ref= faz o mesmo (conveniência para teste no navegador)."""

    def _responder(self, dados):
        from .services import plano_proposta
        ref = dados.get("ref") if hasattr(dados, "get") else None
        if ref in (None, ""):
            return Response({"erro": "Informe 'ref' (índice 1..N ou id_usuario UUID).", "tempo_resposta_ms": 0.0},
                            status=status.HTTP_400_BAD_REQUEST)
        return _executar(plano_proposta.proposta, str(ref), data_corte=dados.get("data_corte"))

    def get(self, request):
        return self._responder(request.GET)

    def post(self, request):
        return self._responder(request.data if isinstance(request.data, dict) else {})


class UsuarioRealPerguntaAPI(APIView):
    """POST usuario-real/<ref>/pergunta/ {"pergunta": "..."} — roteia para uma visão, sem LLM."""

    def post(self, request, referencia):
        pergunta = request.data.get("pergunta") if isinstance(request.data, dict) else None
        if not isinstance(pergunta, str) or not pergunta.strip():
            return Response({"erro": "Informe 'pergunta' (texto).", "tempo_resposta_ms": 0.0},
                            status=status.HTTP_400_BAD_REQUEST)
        return _executar(usuario_real.responder_pergunta, referencia, pergunta.strip(),
                         data_corte=request.data.get("data_corte"))
