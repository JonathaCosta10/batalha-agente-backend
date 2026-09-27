"""
Repositório de clientes com suporte a banco de dados SQLite persistente e grupos fixos F/M.
Garante no backend Django:
1. Grupo Fixo Feminino ('F'): Exatamente 500 clientes indexados (ID % 2 == 0)
2. Grupo Fixo Masculino ('M'): Exatamente 500 clientes indexados (ID % 2 != 0)
3. Total: 1.000 clientes com consulta por ID, gênero ou sorteio randômico.
4. Consulta via SQLite persistente com fallback determinístico de alta performance.
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import random
import sqlite3

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / 'db.sqlite3'

# Listas de nomes para síntese determinística
NOMES_F = [
    "Ana", "Beatriz", "Camila", "Daniela", "Eduarda", "Fernanda", "Gabriela",
    "Helena", "Isabela", "Juliana", "Larissa", "Mariana", "Natália", "Patrícia",
    "Rafaela", "Sofia", "Tatiane", "Vanessa", "Yasmin", "Carolina"
]

NOMES_M = [
    "Alexandre", "Bruno", "Carlos", "Diego", "Eduardo", "Felipe", "Gabriel",
    "Henrique", "Igor", "João", "Lucas", "Mateus", "Nicolas", "Otávio",
    "Paulo", "Rafael", "Rodrigo", "Thiago", "Vinícius", "Vitor"
]

SOBRENOMES = [
    "Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves",
    "Pereira", "Lima", "Gomes", "Costa", "Ribeiro", "Martins", "Carvalho",
    "Almeida", "Lopes", "Soares", "Fernandes", "Vieira", "Barbosa"
]

ID_MINIMO = 1
ID_MAXIMO = 1000


class ClienteForaDoRecorte(LookupError):
    """O id pedido não pertence ao recorte de 1.000 clientes (1..1000)."""

    def __init__(self, cliente_id):
        self.cliente_id = cliente_id
        super().__init__(
            f"Cliente {cliente_id} não existe: o recorte tem os ids {ID_MINIMO} a {ID_MAXIMO}."
        )


def validar_id_no_recorte(cliente_id: int) -> int:
    """Devolve o id se estiver em 1..1000; senão levanta ClienteForaDoRecorte.
    Não há dobra: 1042 NÃO vira 42 (antes de 2026-09-27 virava)."""
    if isinstance(cliente_id, bool) or not isinstance(cliente_id, int):
        raise ClienteForaDoRecorte(cliente_id)
    if cliente_id < ID_MINIMO or cliente_id > ID_MAXIMO:
        raise ClienteForaDoRecorte(cliente_id)
    return cliente_id


def gerar_cliente_por_id(cliente_id: int) -> Dict[str, Any]:
    """
    Gera o cliente do recorte determinístico dos 1.000 perfis:
      - ID % 2 == 0 -> Grupo Fixo Feminino ('F')
      - ID % 2 != 0 -> Grupo Fixo Masculino ('M')
    Ids fora de 1..1000 levantam ClienteForaDoRecorte.
    """
    validar_id_no_recorte(cliente_id)

    is_feminino = (cliente_id % 2 == 0)
    genero = 'F' if is_feminino else 'M'
    grupo_fixo = 'GRUPO_FIXO_FEMININO' if is_feminino else 'GRUPO_FIXO_MASCULINO'
    
    if is_feminino:
        nome_base = NOMES_F[(cliente_id // 2) % len(NOMES_F)]
    else:
        nome_base = NOMES_M[((cliente_id - 1) // 2) % len(NOMES_M)]
    
    sobrenome = SOBRENOMES[(cliente_id * 7) % len(SOBRENOMES)]
    nome_completo = f"{nome_base} {sobrenome}"

    # Cálculo do Score Comportamental (0 a 1000)
    base_score = ((cliente_id * 37) % 850) + 150
    score_comportamental = min(1000, max(120, base_score))

    # Ponto de Índice de Corte (Behavioral Cutoff)
    if score_comportamental >= 750:
        indice_corte = "ALTA_PROPENSAO"
        segmento = "Itaú Personnalité" if score_comportamental > 850 else "Itaú Uniclass"
        diretriz_comportamental = "Abordagem consultiva, sofisticada e proativa. Enfatizar rentabilidade, benefícios exclusivos e assessoria especializada."
    elif score_comportamental >= 450:
        indice_corte = "MEDIA_PROPENSAO"
        segmento = "Itaú Uniclass"
        diretriz_comportamental = "Abordagem equilibrada e orientada a metas. Foco em otimização de fluxo financeiro, seguros e planejamento estruturado."
    else:
        indice_corte = "BAIXA_PROPENSAO"
        segmento = "Itaú Varejo"
        diretriz_comportamental = "Abordagem didática, acolhedora e de alívio financeiro. Priorizar controle de gastos, microcrédito e reserva de emergência."

    saldo_estimado = round(1500.0 + ((score_comportamental * 28.5) % 45000), 2)
    limite_cartao = round(2000.0 + ((score_comportamental * 35.0) % 65000), 2)

    return {
        "id": cliente_id,
        "nome": nome_completo,
        "primeiro_nome": nome_base,
        "genero": genero,
        "grupo_fixo": grupo_fixo,
        "score_comportamental": score_comportamental,
        "indice_corte": indice_corte,
        "segmento": segmento,
        "saldo_estimado": saldo_estimado,
        "limite_cartao": limite_cartao,
        "diretriz_comportamental": diretriz_comportamental,
        "tempo_relacionamento_meses": 12 + ((cliente_id * 3) % 120),
        "chave_pix_preferencial": f"{nome_base.lower()}.{sobrenome.lower()}@email.com",
    }

class RepositorioClientes:
    """
    Gerencia a base indexada de 1.000 clientes no backend Django,
    dividida exatamente nos dois grupos fixos (500 Femininos e 500 Masculinos).
    """
    _cache: Dict[int, Dict[str, Any]] = {}

    @classmethod
    def get_by_id(cls, cliente_id: int) -> Dict[str, Any]:
        """Recupera cliente do banco SQLite ou gera determinístico.
        Levanta ClienteForaDoRecorte para ids fora de 1..1000."""
        validar_id_no_recorte(cliente_id)
        if cliente_id in cls._cache:
            return cls._cache[cliente_id]

        if DB_PATH.exists():
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT cliente_id, nome, primeiro_nome, genero, score_comportamental,
                           indice_corte, segmento, saldo_estimado, limite_cartao, diretriz_comportamental
                    FROM recomendacao_clienteregistro
                    WHERE cliente_id = ?
                """, (cliente_id,))
                row = cursor.fetchone()
                conn.close()

                if row:
                    cliente = {
                        "id": row[0],
                        "nome": row[1],
                        "primeiro_nome": row[2],
                        "genero": row[3],
                        "grupo_fixo": "GRUPO_FIXO_FEMININO" if row[3] == "F" else "GRUPO_FIXO_MASCULINO",
                        "score_comportamental": row[4],
                        "indice_corte": row[5],
                        "segmento": row[6],
                        "saldo_estimado": float(row[7]),
                        "limite_cartao": float(row[8]),
                        "diretriz_comportamental": row[9],
                        "tempo_relacionamento_meses": 12 + ((row[0] * 3) % 120),
                        "chave_pix_preferencial": f"{row[2].lower()}@itau.com.br",
                    }
                    cls._cache[cliente_id] = cliente
                    return cliente
            except Exception:
                pass

        # Fallback determinístico
        cliente = gerar_cliente_por_id(cliente_id)
        cls._cache[cliente_id] = cliente
        return cliente

    @classmethod
    def get_random(cls, genero: Optional[str] = None) -> Dict[str, Any]:
        """
        Retorna um cliente randômico.
        Se genero for 'F', sorteia apenas entre os IDs pares (Grupo Fixo Feminino: 2, 4, 6... 1000).
        Se genero for 'M', sorteia apenas entre os IDs ímpares (Grupo Fixo Masculino: 1, 3, 5... 999).
        """
        if genero == 'F':
            # 500 IDs pares
            random_id = random.randrange(2, 1002, 2)
        elif genero == 'M':
            # 500 IDs ímpares
            random_id = random.randrange(1, 1001, 2)
        else:
            random_id = random.randint(1, 1000)

        return cls.get_by_id(random_id)

    @classmethod
    def get_grupo_fixo(cls, genero: str, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Retorna a lista de clientes pertencentes ao grupo fixo solicitado ('F' ou 'M').
        Total de cada grupo fixo no backend: 500 clientes.
        """
        genero_upper = genero.upper()
        if genero_upper == 'F':
            ids = [i for i in range(2, 1001, 2)]
        else:
            ids = [i for i in range(1, 1000, 2)]

        fatia = ids[offset:offset + limit]
        return [cls.get_by_id(i) for i in fatia]

    @classmethod
    def get_sample_list(cls, limit: int = 20) -> List[Dict[str, Any]]:
        return [cls.get_by_id(i) for i in range(1, limit + 1)]

    @classmethod
    def get_estatisticas_grupos(cls) -> Dict[str, Any]:
        """Estatísticas dos grupos fixos feminino e masculino no backend."""
        return {
            "total_geral": 1000,
            "grupo_fixo_feminino": {
                "genero": "F",
                "total": 500,
                "regra_id": "IDs pares (ID % 2 == 0)",
                "intervalo_ids": "2 a 1000",
                "template_padrao": "TEXTO_3[FEMININO]",
            },
            "grupo_fixo_masculino": {
                "genero": "M",
                "total": 500,
                "regra_id": "IDs ímpares (ID % 2 != 0)",
                "intervalo_ids": "1 a 999",
                "template_padrao": "TEXTO_2[MASCULINO]",
            },
            "grupo_neutro": {
                "descricao": "Disponível para ambos os grupos como template coringa",
                "template_padrao": "TEXTO_1[NEUTRO]",
            }
        }
