"""
Consultas do estudo i.agora (notebooks/estudo-i-agora/i.agora-checkpoint.ipynb) como funções puras.

Cada função reproduz uma consulta do notebook sobre a base transacional real
(`bq-results-*.csv`: id_usuario, mes, tipo, macro, valor, valor_direcional).
A célula de origem e os avisos de cada uma estão em docs/estudo-i-agora/consultas.md.

Diferenças deliberadas em relação ao notebook:
- Nenhuma função gera dados sintéticos; quem chama entrega a base.
- Categoria esperada e ausente é erro, não coluna zerada (a célula 36 zerava
  'Flexivel' e 'Banco' em silêncio e devolvia Score de Flexibilidade 20% para todos).
"""

import pandas as pd

from desafio_itau import politica as _politica

COLUNAS_TRANSACOES = ["id_usuario", "mes", "tipo", "macro", "valor", "valor_direcional"]

# Macros observadas na base real (célula 3, groupby macro/tipo: 30.000 linhas cada).
MACRO_RENDA = "Renda"
MACRO_ESSENCIAL = "Casa/Essencial"
MACRO_FLEXIVEL = "Flexivel/Delivery"
MACRO_SUPERFLUO = "Superfluo"
MACRO_BANCO = "Banco/Taxas"
MACROS_SAIDA = [MACRO_ESSENCIAL, MACRO_FLEXIVEL, MACRO_SUPERFLUO, MACRO_BANCO]

# Limiares do estudo (células 13, 31 e 33).
# Fonte única: t3.limiar_surplus (desafio_itau/politica/operacional-v1.json). Antes: 15 literal duplicado.
LIMIAR_SOBRA_SAUDAVEL_PCT = int(_politica.parametro('t3.limiar_surplus', 'limiar_fracao') * 100)
CLUSTER_ENDIVIDADO = "1. Endividado (< 0)"
CLUSTER_VULNERAVEL = "2. Vulnerável (< 15%)"
CLUSTER_SAUDAVEL = "3. Saudável (>= 15%)"

FAIXAS_SALARIAIS = ["Até R$ 2.500", "R$ 2.501 a R$ 5.000", "R$ 5.001 a R$ 10.000", "Acima de R$ 10.000"]

NIVEL_1 = "Nível 1 (Supérfluo/Lazer - Cortar Primeiro)"
NIVEL_2 = "Nível 2 (Flexível - Reduzir)"
NIVEL_3 = "Nível 3 (Essencial - Não Cortar)"

# Matriz do Passo 4 (célula 38). Taxas digitadas no notebook; nenhuma veio de um RAG executado.
MATRIZ_PRODUTOS = {
    CLUSTER_ENDIVIDADO: "Renegociação IA / Crédito Consolidado (Taxa Aterrada via RAG: 1.49% a.m.)",
    CLUSTER_VULNERAVEL: "Reserva Automática / Seguro Conta (Proteção com Liquidez Diária)",
    CLUSTER_SAUDAVEL: "CDB Itaú Diário / Fundos Multimercado (Rendimento 100% CDI)",
}


def carregar_transacoes(caminho) -> pd.DataFrame:
    """C01 — lê o CSV do BigQuery e recusa base sem as seis colunas esperadas."""
    df = pd.read_csv(caminho)
    if "Table name" in str(df.columns[0]):
        df = pd.read_csv(caminho, skiprows=1)
    df.columns = df.columns.str.strip().str.lower()
    validar_transacoes(df)
    return df


COLUNAS_EXTRATO_REAL = ["id_usuario", "anomes", "tipo", "vlr", "nom_cate_macro", "nom_cate_micro"]


def normalizar_extrato(extrato: pd.DataFrame) -> pd.DataFrame:
    """Converte a tabela real `hackathon_dados.extrato_sintetico` para a forma das consultas.

    mes = anomes (AAAAMM); macro = nom_cate_macro; valor = |vlr|; valor_direcional = +valor em E, -valor em S.
    A taxonomia real NÃO tem as macros Casa/Essencial, Flexivel/Delivery, Superfluo e Banco/Taxas;
    por isso score_de_flexibilidade recusa a base real até que o mapeamento seja decidido.
    """
    faltando = [c for c in COLUNAS_EXTRATO_REAL if c not in extrato.columns]
    if faltando:
        raise ValueError(f"Extrato sem as colunas {faltando}.")
    valor = extrato["vlr"].abs()
    df = pd.DataFrame({
        "id_usuario": extrato["id_usuario"],
        "mes": extrato["anomes"],
        "tipo": extrato["tipo"],
        "macro": extrato["nom_cate_macro"],
        "micro": extrato["nom_cate_micro"],
        "valor": valor,
        "valor_direcional": valor.where(extrato["tipo"] == "E", -valor),
    })
    validar_transacoes(df)
    return df


def validar_transacoes(df: pd.DataFrame) -> None:
    faltando = [c for c in COLUNAS_TRANSACOES if c not in df.columns]
    if faltando:
        raise ValueError(f"Base transacional sem as colunas {faltando}.")
    tipos = set(df["tipo"].unique()) - {"E", "S"}
    if tipos:
        raise ValueError(f"Coluna tipo com valores fora de E/S: {sorted(tipos)}.")


def composicao_por_macro(df: pd.DataFrame) -> pd.DataFrame:
    """C02 — contagem, soma e médias por macro e tipo (célula 3)."""
    return (
        df.groupby(["macro", "tipo"])
        .agg(
            quantidade_transacoes=("valor", "count"),
            soma_valor=("valor", "sum"),
            media_valor=("valor", "mean"),
            media_direcional=("valor_direcional", "mean"),
        )
        .reset_index()
        .sort_values("quantidade_transacoes", ascending=False)
    )


def agregar_mensal(df: pd.DataFrame) -> pd.DataFrame:
    """C07 — entradas, saídas, saldo e % de sobra por cliente e mês (células 31 e 33)."""
    base = df.assign(
        entrada=df["valor_direcional"].where(df["valor_direcional"] > 0, 0.0),
        saida=(-df["valor_direcional"]).where(df["valor_direcional"] < 0, 0.0),
    )
    mensal = base.groupby(["id_usuario", "mes"], as_index=False).agg(
        entradas=("entrada", "sum"), saidas=("saida", "sum")
    )
    mensal["saldo"] = mensal["entradas"] - mensal["saidas"]
    mensal["pct_sobra"] = (mensal["saldo"] / mensal["entradas"].where(mensal["entradas"] > 0)) * 100
    mensal["pct_sobra"] = mensal["pct_sobra"].fillna(0.0)
    return mensal


def classificar_saude(saldo: float, pct_sobra: float) -> str:
    """C05 — regra dos três grupos: saldo < 0; sobra < 15%; sobra >= 15%."""
    if saldo < 0:
        return CLUSTER_ENDIVIDADO
    if pct_sobra < LIMIAR_SOBRA_SAUDAVEL_PCT:
        return CLUSTER_VULNERAVEL
    return CLUSTER_SAUDAVEL


def classificar_faixa_salarial(renda: float) -> str:
    """C03 — faixas de renda mensal (células 9, 21 e 31)."""
    if renda <= 2500:
        return FAIXAS_SALARIAIS[0]
    if renda <= 5000:
        return FAIXAS_SALARIAIS[1]
    if renda <= 10000:
        return FAIXAS_SALARIAIS[2]
    return FAIXAS_SALARIAIS[3]


def perfil_anual(mensal: pd.DataFrame) -> pd.DataFrame:
    """C07 — média anual por cliente, cluster financeiro e faixa salarial."""
    perfil = mensal.drop(columns=["mes"]).groupby("id_usuario", as_index=False).mean(numeric_only=True)
    perfil["cluster_financeiro"] = [classificar_saude(s, p) for s, p in zip(perfil["saldo"], perfil["pct_sobra"])]
    perfil["faixa_salarial"] = perfil["entradas"].apply(classificar_faixa_salarial)
    return perfil


def concentracao_de_gastos(df: pd.DataFrame) -> pd.DataFrame:
    """C11 (Passo 1.2) — % de cada macro no total de saídas."""
    gastos = df[df["tipo"] == "S"].groupby("macro", as_index=False)["valor"].sum()
    gastos["pct"] = gastos["valor"] / gastos["valor"].sum() * 100
    return gastos.sort_values("pct", ascending=False)


def coorte_negativada(mensal: pd.DataFrame, mes: int = 12) -> pd.DataFrame:
    """C08 — clientes com saldo < 0 no mês; divida_atual é o módulo do saldo."""
    alvo = mensal[(mensal["mes"] == mes) & (mensal["saldo"] < 0)][["id_usuario", "saldo"]].copy()
    alvo["divida_atual"] = alvo.pop("saldo").abs()
    return alvo


def evolucao_da_coorte(mensal: pd.DataFrame, ids) -> pd.DataFrame:
    """C08 — "Tesoura de Liquidez": médias mensais de entradas e saídas da coorte."""
    return (
        mensal[mensal["id_usuario"].isin(ids)]
        .groupby("mes", as_index=False)[["entradas", "saidas", "saldo"]]
        .mean()
    )


def score_de_flexibilidade(df: pd.DataFrame, coorte: pd.DataFrame, mes: int = 12) -> pd.DataFrame:
    """C09 — % das saídas do mês em Flexível + Supérfluo, e meta de economia em 6 meses.

    Recusa a base se faltar alguma macro de saída: é o erro que a célula 36 escondia.
    """
    saidas = df[(df["tipo"] == "S") & (df["mes"] == mes) & (df["id_usuario"].isin(coorte["id_usuario"]))]
    tabela = saidas.groupby(["id_usuario", "macro"])["valor"].sum().unstack(fill_value=0.0)
    faltando = [m for m in MACROS_SAIDA if m not in tabela.columns]
    if faltando:
        raise ValueError(f"Macros de saída ausentes {faltando}; o score seria calculado sobre categorias zeradas.")
    tabela = tabela.reset_index()
    tabela["total_gastos"] = tabela[MACROS_SAIDA].sum(axis=1)
    tabela["score_de_flexibilidade_pct"] = (tabela[MACRO_FLEXIVEL] + tabela[MACRO_SUPERFLUO]) / tabela["total_gastos"] * 100
    tabela = tabela.merge(coorte, on="id_usuario")
    tabela["meta_de_economia_mensal"] = meta_de_economia_mensal(tabela["divida_atual"])
    return tabela


def meta_de_economia_mensal(divida, meses: int = 6):
    """C09 — dívida dividida em parcelas iguais (6 meses no estudo, sem juros)."""
    if meses <= 0:
        raise ValueError("meses precisa ser positivo.")
    return divida / meses


def classificar_essencialidade(categoria: str) -> str:
    """C10 — matriz de essencialidade por palavra-chave (células 27 e 29)."""
    texto = str(categoria).lower()
    if any(p in texto for p in ["casa", "mercado", "saúde", "educacao"]):
        return NIVEL_3
    if any(p in texto for p in ["restaurante", "cuidados", "transporte"]):
        return NIVEL_2
    return NIVEL_1


def margem_de_corte_seguro(nivel_1: float, nivel_2: float) -> float:
    """C10 — corta 100% do Nível 1 e 50% do Nível 2; Nível 3 fica intacto."""
    return nivel_1 + nivel_2 * 0.5


def diagnostico_50_30_20(pct_fixo: float, pct_variavel: float, pct_investimento: float) -> str:
    """C06 — primeira regra que casa, na ordem da célula 19 (limiares 53 / 33 / 10)."""
    if pct_fixo > 53:
        return "Alerta Fixo"
    if pct_variavel > 33:
        return "Oportunidade Variável"
    if pct_investimento < 10:
        return "Construção de Futuro"
    return "Perfil Equilibrado"


def recomendar_produto(cluster: str) -> str:
    """C13 (Passo 4) — produto da matriz para o cluster; cluster desconhecido é erro."""
    if cluster not in MATRIZ_PRODUTOS:
        raise ValueError(f"Cluster sem produto na matriz: {cluster!r}.")
    return MATRIZ_PRODUTOS[cluster]
