"""
Views da aplicação de Recomendação e Agentes Contextuais.
Implementa endpoints RESTful em formato JSON para integração com o App Android Demo
e views baseadas em templates Django para renderização server-side.
Inclui gestão da Chave ON-OFF 'inteiração-tela-iai' no Backend Django.
"""

from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import render, redirect
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .services.customer_repository import RepositorioClientes, ClienteForaDoRecorte
from .services.behavioral_score import BehavioralScoreEngine
from .services.template_engine import TemplateEngine, PLANILHA_FIXA_PRODUTOS

# ==============================================================================
# APIs RESTful (Arquitetura para consumo pelo App Android / Frontend)
# ==============================================================================

class ChaveInteracaoTelaIAIAPI(APIView):
    """
    Controla e audita a chave ON - OFF sobre o ponto de 'inteiração-tela-iai' no backend:
    - GET: Retorna o estado atual da chave ('ON' ou 'OFF') e o template ativo resultante.
    - POST: Atualiza a chave no banco de dados SQLite {'chave_ativa': true / false}
    Com a chave ON: Liga o modo 'Neutro' como padrão para Maria, João e todos os clientes.
    """
    def get(self, request):
        ativa = TemplateEngine.get_chave_interacao_tela_iai()
        return Response({
            "codigo": "CHAVE_INTEIRACAO_TELA_IAI",
            "nome": "Ponto de Inteiração Tela-IAI",
            "estado": "ON" if ativa else "OFF",
            "chave_ativa": ativa,
            "comportamento": "MODO_NEUTRO_UNIVERSAL" if ativa else "MODO_BIFURCACAO_GENERO_ESTRITA",
            "exemplos": {
                "feminino_exemplo": {
                    "cliente": "Maria",
                    "saudacao": "Que bom ter você aqui, Maria!",
                    "tag_ativa": "TEXTO_1[NEUTRO]" if ativa else "TEXTO_3[FEMININO]",
                },
                "masculino_exemplo": {
                    "cliente": "Joao",
                    "saudacao": "Que bom ter você aqui, Joao!",
                    "tag_ativa": "TEXTO_1[NEUTRO]" if ativa else "TEXTO_2[MASCULINO]",
                }
            }
        }, status=status.HTTP_200_OK)

    def post(self, request):
        """
        Corpo aceito: {} (alterna) ou {"chave_ativa": true|false} (JSON boolean).
        Qualquer outro tipo — "false" em texto, 0, null — responde 400 {erro}:
        antes, bool("false") ligava a chave.
        Se a gravação falhar responde 500 {erro}, sem afirmar sucesso.
        """
        if not isinstance(request.data, dict):
            return Response({"erro": "Envie um objeto JSON: {} ou {\"chave_ativa\": true|false}."},
                            status=status.HTTP_400_BAD_REQUEST)
        if "chave_ativa" not in request.data:
            # Ausência = alternar (toggle)
            novo_valor = not TemplateEngine.get_chave_interacao_tela_iai()
        else:
            valor = request.data["chave_ativa"]
            if not isinstance(valor, bool):
                return Response({"erro": "O campo 'chave_ativa' deve ser JSON boolean (true ou false); omita-o para alternar."},
                                status=status.HTTP_400_BAD_REQUEST)
            novo_valor = valor

        if not TemplateEngine.set_chave_interacao_tela_iai(novo_valor):
            return Response({"erro": "Não foi possível gravar a chave no banco de dados; o estado não foi alterado."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        gravado = TemplateEngine.get_chave_interacao_tela_iai()  # relido do banco, não o valor pedido
        return Response({
            "mensagem": "Chave atualizada com sucesso no backend Django",
            "chave_ativa": gravado,
            "estado": "ON" if gravado else "OFF",
            "modo_ativo": "NEUTRO" if gravado else "SEGMENTADO"
        }, status=status.HTTP_200_OK)


def _resposta_cliente_inexistente(erro: ClienteForaDoRecorte) -> Response:
    """404 {erro} para ids fora do recorte 1..1000 (sem dobra de ids)."""
    return Response({"erro": str(erro)}, status=status.HTTP_404_NOT_FOUND)


def _cliente_ou_404_html(cliente_id: int):
    """Para as páginas HTML: Http404 em vez de dobrar o id."""
    try:
        return RepositorioClientes.get_by_id(cliente_id)
    except ClienteForaDoRecorte as erro:
        raise Http404(str(erro))


class ClienteDetalheAPI(APIView):
    """Retorna dados de um cliente específico no recorte dos 1.000 perfis."""
    def get(self, request, cliente_id):
        try:
            cid = int(cliente_id)
            cliente = RepositorioClientes.get_by_id(cid)
            return Response(cliente, status=status.HTTP_200_OK)
        except ClienteForaDoRecorte as e:
            return _resposta_cliente_inexistente(e)
        except Exception as e:
            return Response({"erro": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ClienteRandomicoAPI(APIView):
    """
    Sorteia um dos clientes da base no backend Django.
    Aceita query parameter '?genero=F' ou '?genero=M' para sortear estritamente
    dentro do respectivo Grupo Fixo Feminino ou Grupo Fixo Masculino.
    """
    def get(self, request):
        genero = request.GET.get('genero', '').upper()
        if genero not in ['F', 'M']:
            genero = None
        cliente = RepositorioClientes.get_random(genero=genero)
        return Response(cliente, status=status.HTTP_200_OK)

class GruposFixosAPI(APIView):
    """
    Endpoint centralizado do Backend Django para auditoria dos Grupos Fixos F e M:
    - Retorna contagem de 500 Femininos (IDs pares) e 500 Masculinos (IDs ímpares).
    - Lista amostras de cada grupo e mapeamento dos templates vinculados.
    """
    def get(self, request):
        stats = RepositorioClientes.get_estatisticas_grupos()
        amostra_f = RepositorioClientes.get_grupo_fixo(genero='F', limit=5)
        amostra_m = RepositorioClientes.get_grupo_fixo(genero='M', limit=5)
        chave_on = TemplateEngine.get_chave_interacao_tela_iai()

        return Response({
            "status": "success",
            "chave_interacao_tela_iai": "ON" if chave_on else "OFF",
            "estatisticas": stats,
            "amostras": {
                "grupo_fixo_feminino_amostra": amostra_f,
                "grupo_fixo_masculino_amostra": amostra_m,
            }
        }, status=status.HTTP_200_OK)

class ChatVariavel1API(APIView):
    """
    Retorna a conversa pré-preenchida (Variável 1).
    Baseia-se no ID (1-1000) e respeita a chave 'inteiração-tela-iai':
    - Se chave ON (padrão): Retorna TEXTO_1[NEUTRO] com saudação 'Que bom ter você aqui, [Nome]!'
    - Se chave OFF: Retorna TEXTO_3 para F ou TEXTO_2 para M.
    """
    def get(self, request, cliente_id):
        try:
            cid = int(cliente_id)
            cliente = RepositorioClientes.get_by_id(cid)
            chat_data = TemplateEngine.gerar_chat_variavel_1(cliente)
            return Response({
                "cliente": {
                    "id": cliente["id"],
                    "nome": cliente["nome"],
                    "primeiro_nome": cliente["primeiro_nome"],
                    "genero": cliente["genero"],
                    "grupo_fixo": cliente.get("grupo_fixo"),
                    "score": cliente["score_comportamental"]
                },
                "chave_interacao_tela_iai": chat_data.get("chave_interacao_tela_iai"),
                "modo_ativo": chat_data.get("modo_ativo"),
                "chat_variavel_1": chat_data
            }, status=status.HTTP_200_OK)
        except ClienteForaDoRecorte as e:
            return _resposta_cliente_inexistente(e)
        except Exception as e:
            return Response({"erro": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ComunicacaoEAgoraAPI(APIView):
    """
    Disparado pelo clique no botão 'E agora?' no final do chat.
    Gera a interface de comunicação baseada no Template 3 (Planilha Fixa)
    e na contextualização orientada a dados de comportamento do cliente.
    """
    def get(self, request, cliente_id):
        try:
            cid = int(cliente_id)
            cliente = RepositorioClientes.get_by_id(cid)
            payload = TemplateEngine.gerar_template_3_comunicacao(cliente)
            return Response(payload, status=status.HTTP_200_OK)
        except ClienteForaDoRecorte as e:
            return _resposta_cliente_inexistente(e)
        except Exception as e:
            return Response({"erro": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request, cliente_id):
        return self.get(request, cliente_id)

class ContextoScoreAPI(APIView):
    """Retorna o Ponto de Índice e o score de corte para contextualizar o agente."""
    def get(self, request, cliente_id):
        try:
            cid = int(cliente_id)
            cliente = RepositorioClientes.get_by_id(cid)
            score_context = BehavioralScoreEngine.calcular_indice_contexto(cliente)
            return Response(score_context, status=status.HTTP_200_OK)
        except ClienteForaDoRecorte as e:
            return _resposta_cliente_inexistente(e)
        except Exception as e:
            return Response({"erro": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class PlanilhaFixaAPI(APIView):
    """Retorna os dados da planilha fixa de produtos para auditoria e templates."""
    def get(self, request):
        return Response({
            "descricao": "Planilha Fixa de Produtos e Regras do Desafio Itaú",
            "total_itens": len(PLANILHA_FIXA_PRODUTOS),
            "itens": PLANILHA_FIXA_PRODUTOS
        }, status=status.HTTP_200_OK)

# ==============================================================================
# Views Django baseadas em Templates HTML (Server-Side)
# ==============================================================================

class DashboardView(View):
    """Painel geral do projeto Django com visão dos grupos fixos e 1000 clientes."""
    def get(self, request):
        # Consequência da remoção da dobra de ids: ?cliente_id fora de 1..1000
        # (ou não numérico, que antes dava 500) passa a responder 404.
        try:
            cliente_id = int(request.GET.get('cliente_id', 42))
        except (TypeError, ValueError):
            raise Http404("cliente_id deve ser um número de 1 a 1000.")
        cliente = _cliente_ou_404_html(cliente_id)
        chat_data = TemplateEngine.gerar_chat_variavel_1(cliente)
        template_3 = TemplateEngine.gerar_template_3_comunicacao(cliente)
        amostra_clientes = RepositorioClientes.get_sample_list(limit=10)
        grupos_stats = RepositorioClientes.get_estatisticas_grupos()
        chave_on = TemplateEngine.get_chave_interacao_tela_iai()

        contexto = {
            "cliente_atual": cliente,
            "chat_data": chat_data,
            "template_3": template_3,
            "amostra_clientes": amostra_clientes,
            "grupos_stats": grupos_stats,
            "chave_interacao_tela_iai": "ON" if chave_on else "OFF",
            "total_clientes": 1000,
        }
        return render(request, "recommendations/dashboard.html", contexto)

class TemplateChatView(View):
    """Renderiza a tela de chat pré-preenchida no padrão Django Template."""
    def get(self, request, cliente_id):
        cliente = _cliente_ou_404_html(int(cliente_id))
        chat_data = TemplateEngine.gerar_chat_variavel_1(cliente)
        chave_on = TemplateEngine.get_chave_interacao_tela_iai()
        
        # Se chave ON -> renderiza template neutro
        if chave_on:
            template_name = "recommendations/chat_neutro.html"
        else:
            template_name = "recommendations/chat_f.html" if cliente["genero"] == "F" else "recommendations/chat_m.html"

        return render(request, template_name, {
            "cliente": cliente,
            "chat": chat_data,
            "chave_ativa": chave_on,
        })

class TemplateMatrixView(View):
    """Renderiza a interface de comunicação com a planilha fixa Template 3."""
    def get(self, request, cliente_id):
        cliente = _cliente_ou_404_html(int(cliente_id))
        dados =TemplateEngine.gerar_template_3_comunicacao(cliente)
        return render(request, "recommendations/template_3_matrix.html", dados)
