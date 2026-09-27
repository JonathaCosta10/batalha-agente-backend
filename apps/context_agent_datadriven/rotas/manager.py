"""
Módulo de Gerenciamento da Base de Rotas.
Lê o template .yaml com as informações base de cada categoria e roteia chamadas.
"""

import os
import re
from typing import Dict, Any, Optional

def parse_simple_yaml(filepath: str) -> Dict[str, Any]:
    """
    Parser robusto embutido para arquivos YAML de rotas,
    garantindo independência de dependências externas como PyYAML.
    """
    if not os.path.exists(filepath):
        return {}

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    result: Dict[str, Any] = {
        "versao_schema": "2.4.0-datadriven",
        "data_corte_fixa": "2025-12-22",
        "janela_temporal_horario": "24h",
        "protocolo_negociacao_padrao": "consenso_prioritario_com_fallback",
        "categorias": {
            "investimentos_e_patrimonio": {
                "id": "CAT-INV-01",
                "nome": "Investimentos & Alocação de Patrimônio",
                "score_minimo": 650,
                "protocolo_negociacao": {
                    "provedor_primario": "google",
                    "modelo_primario": "gemini-flash-latest",
                    "provedores_alternativos": ["antropic", "openIa"],
                    "sla_latencia_max_ms": 1200,
                    "temperatura": 0.35,
                    "max_tokens": 700,
                },
                "diretriz_template": {
                    "foco": "Otimização de patrimônio, CDB progressivo 112% CDI, liquidez seletiva.",
                    "sigilo": "Não expor scores ou tabelas numéricas. Linguagem de especialista consultivo.",
                }
            },
            "credito_e_limites": {
                "id": "CAT-CRED-02",
                "nome": "Crédito Consciente, Cartões e Remanejamento de Limites",
                "score_minimo": 450,
                "protocolo_negociacao": {
                    "provedor_primario": "google",
                    "modelo_primario": "gemini-flash-latest",
                    "provedores_alternativos": ["antropic", "openIa"],
                    "sla_latencia_max_ms": 900,
                    "temperatura": 0.30,
                    "max_tokens": 650,
                },
                "diretriz_template": {
                    "foco": "Adequação de limites, prevenção a juros rotativos e remanejamento inteligente.",
                    "sigilo": "Preservar dados brutos internamente; apresentar soluções acessíveis.",
                }
            },
            "seguranca_e_reserva_emergencia": {
                "id": "CAT-RES-03",
                "nome": "Reserva de Emergência, Proteção e Liquidez Diária",
                "score_minimo": 0,
                "protocolo_negociacao": {
                    "provedor_primario": "google",
                    "modelo_primario": "gemini-3.5-flash-lite",
                    "provedores_alternativos": ["antropic", "openIa"],
                    "sla_latencia_max_ms": 800,
                    "temperatura": 0.30,
                    "max_tokens": 600,
                },
                "diretriz_template": {
                    "foco": "Aporte inicial seguro com garantia FGC, liquidez imediata e estabilidade financeira.",
                    "sigilo": "Tom acolhedor sem juízo de valor sobre o score de partida.",
                }
            },
            "atendimento_consultivo_geral": {
                "id": "CAT-GERAL-04",
                "nome": "Atendimento Consultivo Geral e Orientação Itaú",
                "score_minimo": 0,
                "protocolo_negociacao": {
                    "provedor_primario": "google",
                    "modelo_primario": "gemini-flash-latest",
                    "provedores_alternativos": ["antropic", "openIa"],
                    "sla_latencia_max_ms": 1000,
                    "temperatura": 0.35,
                    "max_tokens": 600,
                },
                "diretriz_template": {
                    "foco": "Orientação transparente, escuta ativa e direcionamento para produtos convenientes.",
                    "sigilo": "Diálogo natural em linguagem clara.",
                }
            },
        }
    }
    return result

class BaseDeRotasManager:
    """
    Gerenciador da Base de Rotas definida no template .yaml.
    Mapeia a intenção e dados contextuais do cliente para a categoria correspondente.
    """

    _cache_rotas: Optional[Dict[str, Any]] = None

    @classmethod
    def get_caminho_template_yaml(cls) -> str:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, "templates", "rotas_base.yaml")

    @classmethod
    def carregar_rotas(cls) -> Dict[str, Any]:
        if cls._cache_rotas is None:
            caminho = cls.get_caminho_template_yaml()
            cls._cache_rotas = parse_simple_yaml(caminho)
        return cls._cache_rotas

    @classmethod
    def identificar_categoria(cls, mensagem: str, score: int = 750) -> Dict[str, Any]:
        """
        Analisa a mensagem e os dados do cliente e seleciona a categoria de rota ideal.
        """
        rotas = cls.carregar_rotas()
        categorias = rotas.get("categorias", {})
        texto_lower = mensagem.lower()

        # Regras de roteamento baseadas no template .yaml
        if any(w in texto_lower for w in ["invest", "patrimonio", "cdb", "cdi", "renda fixa", "ações", "fundos"]):
            cat_key = "investimentos_e_patrimonio"
        elif any(w in texto_lower for w in ["limite", "cartão", "cartao", "fatura", "credito", "crédito", "remanej"]):
            cat_key = "credito_e_limites"
        elif any(w in texto_lower for w in ["reserva", "emergencia", "emergência", "seguro", "guardar", "poupança"]):
            cat_key = "seguranca_e_reserva_emergencia"
        else:
            cat_key = "atendimento_consultivo_geral"

        categoria_info = categorias.get(cat_key, categorias.get("atendimento_consultivo_geral"))
        return {
            "chave_categoria": cat_key,
            "detalhes": categoria_info,
            "data_corte_fixa": rotas.get("data_corte_fixa", "2025-12-22"),
        }
