"""
Engine de Templates e Comunicação.
Gerencia:
1. Variável 1: Conversa pré-preenchida com chave ON - OFF 'inteiração-tela-iai'.
   - Com Chave ON (Padrão): Liga o modo 'Neutro' como template ativo universal (ex: Maria e João).
   - Com Chave OFF: Aplica bifurcação estrita por gênero (F -> TEXTO_3 / M -> TEXTO_2).
2. Variável Template 3: Planilha fixa de dados estruturados com regras de propensão e scoring.
3. Montagem da interface de comunicação final com agente contextualizado.
"""

from typing import Dict, Any, List, Optional
from django.db import DatabaseError
from .behavioral_score import BehavioralScoreEngine

# Planilha / Matriz Fixa de Dados de Negócio (Template 3)
PLANILHA_FIXA_PRODUTOS = [
    {
        "codigo": "ITAU-INV-01",
        "produto": "CDB Itaú Personalizado Pós-Fixado",
        "categoria": "Investimentos",
        "taxa_ou_retorno": "104% a 112% do CDI",
        "carencia_prazo": "Liquidez Diária ou 360 dias",
        "score_minimo": 400,
        "publico_alvo": "Geral com reserva ou objetivo de rentabilidade",
        "beneficio_chave": "Garantia FGC e rentabilidade progressiva com aportes programados",
        "afinidade_f": 92,
        "afinidade_m": 88,
    },
    {
        "codigo": "ITAU-CRED-02",
        "produto": "Crédito Sob Medida com Taxa Bonificada",
        "categoria": "Crédito & Fluxo",
        "taxa_ou_retorno": "A partir de 1,19% a.m.",
        "carencia_prazo": "Até 90 dias para 1ª parcela",
        "score_minimo": 300,
        "publico_alvo": "Otimização de capital de giro pessoal e consolidação",
        "beneficio_chave": "Sem cobrança de TAC e contratação 100% digital com liberação imediata via Pix",
        "afinidade_f": 85,
        "afinidade_m": 90,
    },
    {
        "codigo": "ITAU-CARD-03",
        "produto": "Cartão Itaú Carbon Platinum / Black",
        "categoria": "Meios de Pagamento",
        "taxa_ou_retorno": "Pontos Átomos (até 2,5 pts/$) ou Cashback de 1,5%",
        "carencia_prazo": "Anuidade 100% isenta por volume de gastos",
        "score_minimo": 600,
        "publico_alvo": "Alta transacionalidade e viagens",
        "beneficio_chave": "Acesso a salas VIP, tag de pedágio sem mensalidade e seguros de viagem",
        "afinidade_f": 94,
        "afinidade_m": 91,
    },
    {
        "codigo": "ITAU-PREV-04",
        "produto": "Previdência & Planejamento Sucessório",
        "categoria": "Previdência & Futuro",
        "taxa_ou_retorno": "Taxa zero de custódia e carregamento de entrada",
        "carencia_prazo": "Planos PGBL / VGBL a partir de R$ 100/mês",
        "score_minimo": 500,
        "publico_alvo": "Planejamento de longo prazo e eficiência tributária",
        "beneficio_chave": "Dedução de até 12% da renda bruta tributável no IRPF anual",
        "afinidade_f": 89,
        "afinidade_m": 82,
    },
    {
        "codigo": "ITAU-PROT-05",
        "produto": "Seguro Vida & Proteção Integrada",
        "categoria": "Seguros",
        "taxa_ou_retorno": "Prêmio a partir de R$ 19,90/mês",
        "carencia_prazo": "Vigência imediata após confirmação",
        "score_minimo": 200,
        "publico_alvo": "Proteção de renda familiar e cobertura em vida",
        "beneficio_chave": "Assistência funeral familiar, telemedicina Einstein 24h e sorteios mensais",
        "afinidade_f": 96,
        "afinidade_m": 84,
    },
]

class TemplateEngine:
    """Motor de formatação e injeção de templates orientados a dados e banco de dados."""

    CODIGO_CHAVE = "CHAVE_INTEIRACAO_TELA_IAI"

    @staticmethod
    def get_chave_interacao_tela_iai() -> bool:
        """
        Consulta o estado da chave ON - OFF 'CHAVE_INTEIRACAO_TELA_IAI' pelo ORM.
        Padrão: ON (True) quando a linha ainda não existe.
        """
        from ..models import FeatureFlagInteracaoTelaIAI
        try:
            linha = FeatureFlagInteracaoTelaIAI.objects.filter(pk=TemplateEngine.CODIGO_CHAVE).first()
        except DatabaseError:
            linha = None
        return True if linha is None else bool(linha.chave_ativa)

    @staticmethod
    def set_chave_interacao_tela_iai(ativa: bool) -> bool:
        """
        Grava a chave ON - OFF pelo ORM (a tabela vem das migrações; o antigo
        INSERT cru não preenchia atualizado_em e falha no esquema migrado).
        Devolve False se a gravação falhar — quem chama tem de olhar o retorno.
        """
        from ..models import FeatureFlagInteracaoTelaIAI
        try:
            FeatureFlagInteracaoTelaIAI.objects.update_or_create(
                pk=TemplateEngine.CODIGO_CHAVE, defaults={"chave_ativa": bool(ativa)},
            )
        except DatabaseError:
            return False
        return True

    @staticmethod
    def gerar_chat_variavel_1(cliente: Dict[str, Any], forcar_chave: Optional[bool] = None) -> Dict[str, Any]:
        """
        Gera a conversa pré-preenchida (Variável 1).
        Com a Chave 'inteiração-tela-iai' ON (padrão):
          -> Liga o modo 'Neutro' como template ativo universal (ex: Maria e João)
        Com a Chave OFF:
          -> Aplica a variante de gênero (TEXTO_3 para F, TEXTO_2 para M)
        """
        chave_on = TemplateEngine.get_chave_interacao_tela_iai() if forcar_chave is None else forcar_chave
        genero = cliente["genero"]
        primeiro_nome = cliente["primeiro_nome"]

        saudacao_formatada = f"Que bom ter você aqui, {primeiro_nome}!"

        paragrafo_1 = "Hoje, seu dinheiro está concentrado no presente, deixando pouco espaço para imprevistos e planos futuros."
        paragrafo_2 = "Pequenas mudanças podem trazer mais equilíbrio. Você já sabe onde está, chegou a hora de decidir seu próximo passo."

        texto_1_neutro = {
            "tag": "TEXTO_1[NEUTRO]",
            "paragrafo_1": paragrafo_1,
            "paragrafo_2": paragrafo_2,
            "texto_completo": f"{paragrafo_1}\n\n{paragrafo_2}"
        }

        texto_2_masculino = {
            "tag": "TEXTO_2[MASCULINO]",
            "paragrafo_1": paragrafo_1,
            "paragrafo_2": paragrafo_2,
            "texto_completo": f"{paragrafo_1}\n\n{paragrafo_2}"
        }

        texto_3_feminino = {
            "tag": "TEXTO_3[FEMININO]",
            "paragrafo_1": paragrafo_1,
            "paragrafo_2": paragrafo_2,
            "texto_completo": f"{paragrafo_1}\n\n{paragrafo_2}"
        }

        # REGRA DA CHAVE ON-OFF:
        # Se chave ON -> texto ativo é o NEUTRO (para Maria, João ou qualquer cliente)
        # Se chave OFF -> texto ativo segue o gênero (F -> TEXTO_3, M -> TEXTO_2)
        if chave_on:
            texto_ativo = texto_1_neutro
        else:
            texto_ativo = texto_3_feminino if genero == "F" else texto_2_masculino

        return {
            "genero": genero,
            "variavel_nome": primeiro_nome,
            "chave_interacao_tela_iai": "ON" if chave_on else "OFF",
            "modo_ativo": "NEUTRO" if chave_on else ("FEMININO" if genero == "F" else "MASCULINO"),
            "saudacao": saudacao_formatada,
            "saudacao_template": "Que bom ter você aqui,[VARIAVEL_NOME] !",
            "texto_1_neutro": texto_1_neutro,
            "texto_2_masculino": texto_2_masculino,
            "texto_3_feminino": texto_3_feminino,
            "texto_ativo": texto_ativo,
            "titulo_abordagem": "Auditoria Itaú",
            "mensagem_abertura": texto_ativo["texto_completo"],
            "botao_proximo": "E agora?",
        }

    @staticmethod
    def gerar_template_3_comunicacao(cliente: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gera a interface de comunicação disparada pelo botão 'E agora?',
        incorporando a planilha fixa com dados de recomendação e o recorte
        de índice comportamental que orienta o agente de IA.
        """
        score_info = BehavioralScoreEngine.calcular_indice_contexto(cliente)
        genero = cliente["genero"]
        score_cliente = cliente["score_comportamental"]

        # Calcula a pontuação de aderência para cada item da planilha fixa
        tabela_processada = []
        for item in PLANILHA_FIXA_PRODUTOS:
            afinidade_base = item["afinidade_f"] if genero == "F" else item["afinidade_m"]
            fator_score = min(1.0, score_cliente / 1000)
            score_final = int(round(afinidade_base * (0.6 + 0.4 * fator_score)))

            tabela_processada.append({
                **item,
                "score_propensao_cliente": score_final,
                "status_elegibilidade": "Pré-Aprovado" if score_cliente >= item["score_minimo"] else "Em Análise",
            })

        # Ordena a planilha fixa pela propensão calculada
        tabela_processada.sort(key=lambda x: x["score_propensao_cliente"], reverse=True)

        return {
            "template_id": "TEMPLATE_3_FIXED_SPREADSHEET",
            "cliente": {
                "id": cliente["id"],
                "nome": cliente["nome"],
                "genero": genero,
                "score_comportamental": score_cliente,
                "segmento": cliente["segmento"],
            },
            "contexto_agente": score_info,
            "planilha_fixa": tabela_processada,
            "resumo_executivo": (
                f"Interface de comunicação gerada para {cliente['nome']} (ID {cliente['id']}, Gênero {genero}). "
                f"Índice de comportamento: {score_info['indice_code']} ({score_cliente}/1000). "
                f"Diretriz do agente: {score_info['tom_comunicacao']}."
            ),
        }
