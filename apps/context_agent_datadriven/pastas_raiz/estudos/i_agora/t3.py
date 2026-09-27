"""
Segmentação T3 (Vulnerável, Esbanjador, Livre) pelos fluxos Inflow / Outflow / Surplus.

Fonte única da regra: o SQL das visões recebe o mapa de grupos gerado aqui
(`cte_grupos()`), e a classificação em Python (`classificar_t3`) usa as mesmas
constantes. Documentação e números medidos: docs/estudo-i-agora/t3-e-resposta.md.

Janela: meses COMPLETOS antes do mês do corte da tese (22/12/2025 → jan-nov/2025).
Dezembro/2025 vai só até o dia 22 na regra da tese e entraria como mês parcial.

Regra (médias mensais por cliente):
    inflow  = soma |vlr| de tipo E        outflow = soma |vlr| de tipo S
    surplus = inflow - outflow            taxa_surplus = surplus / inflow
    Livre       taxa_surplus >= 15%
    Esbanjador  taxa_surplus < 15%, mas (surplus + discricionário) / inflow >= 15%
                → cortar só o discricionário devolve o cliente a Livre
    Vulnerável  o resto: nem zerando o discricionário chega a 15%
"""

from desafio_itau import politica

# Valor da regra `t3.limiar_surplus` em desafio_itau/politica/operacional-v1.json (antes: literal 0.15 aqui).
# float() de Decimal('0.15') dá 0.15 exatamente como o literal: o SQL renderizado com repr() não muda.
LIMIAR_SURPLUS = float(politica.parametro('t3.limiar_surplus', 'limiar_fracao'))

VULNERAVEL = "Vulnerável"
ESBANJADOR = "Esbanjador"
LIVRE = "Livre"
SEGMENTOS = (VULNERAVEL, ESBANJADOR, LIVRE)

ESSENCIAL = "essencial"
COMPROMISSO = "compromisso_financeiro"
DISCRICIONARIO = "discricionario"
NAO_CLASSIFICADO = "nao_classificado"
GRUPOS = (ESSENCIAL, COMPROMISSO, DISCRICIONARIO, NAO_CLASSIFICADO)

# As 21 macros de saída medidas em q06 (medicoes/2026-09-27/q06_composicao_saidas.json).
# Um teste confere este mapa contra a medição: macro nova na base reprova.
MAPA_GRUPOS = {
    "Casa": ESSENCIAL,
    "Mercado": ESSENCIAL,
    "Educacao": ESSENCIAL,
    "Transporte publico": ESSENCIAL,
    "Posto de combustivel": ESSENCIAL,
    "Veiculos": ESSENCIAL,
    "Emprestimos e financiamentos": COMPROMISSO,
    "Produtos financeiros": COMPROMISSO,
    "Boletos diversos": COMPROMISSO,
    "Lazer": DISCRICIONARIO,
    "Lojas e sites": DISCRICIONARIO,
    "Viagens": DISCRICIONARIO,
    "Restaurantes": DISCRICIONARIO,
    "Delivery": DISCRICIONARIO,
    "Assinaturas": DISCRICIONARIO,
    "Cuidados pessoais": DISCRICIONARIO,
    "Transporte por app": DISCRICIONARIO,
    "Pets": DISCRICIONARIO,
    "Transferencias diversas": NAO_CLASSIFICADO,
    "Outros gastos": NAO_CLASSIFICADO,
    "Saque": NAO_CLASSIFICADO,
}

# Macros de entrada medidas em q02.
TAXONOMIA_ENTRADA = ("Recebimentos diversos", "Salarios e bonificacoes", "Rendimentos", "Beneficios")


def macros_sem_grupo(macros_medidas) -> list[str]:
    """Macros de saída da base que o mapa não cobre. O SQL as marca em saidas_sem_grupo."""
    return sorted(set(macros_medidas) - set(MAPA_GRUPOS))


def _sql_texto(valor: str) -> str:
    if "'" in valor or "\\" in valor:
        raise ValueError(f"Macro com caractere proibido no SQL: {valor!r}.")
    return f"'{valor}'"


def cte_grupos(mapa: dict | None = None) -> str:
    """CTE `grupos(macro, grupo)` gerada do mapa; o SQL das visões usa `{{GRUPOS}}`."""
    mapa = MAPA_GRUPOS if mapa is None else mapa
    invalidos = sorted({g for g in mapa.values() if g not in GRUPOS})
    if invalidos:
        raise ValueError(f"Grupos desconhecidos no mapa: {invalidos}.")
    linhas = [f"SELECT {_sql_texto(m)} AS macro, {_sql_texto(g)} AS grupo" for m, g in sorted(mapa.items())]
    return "grupos AS (\n  " + "\n  UNION ALL ".join(linhas) + "\n)"


def renderizar_sql(sql: str, mapa: dict | None = None) -> str:
    """Preenche `{{GRUPOS}}` e `{{LIMIAR_SURPLUS}}`; marcador que sobrar é erro."""
    sql = sql.replace("{{GRUPOS}}", cte_grupos(mapa)).replace("{{LIMIAR_SURPLUS}}", repr(LIMIAR_SURPLUS))
    if "{{" in sql:
        raise ValueError("SQL com marcador não resolvido.")
    return sql


def classificar_t3(inflow: float, outflow: float, discricionario: float, limiar: float = LIMIAR_SURPLUS) -> str:
    """Regra T3 sobre médias mensais. Sem inflow não há taxa: o cliente é Vulnerável.

    `limiar` só muda na análise de sensibilidade (estatistica.sensibilidade_do_limiar).
    """
    if inflow <= 0:
        return VULNERAVEL
    surplus = inflow - outflow
    if surplus / inflow >= limiar:
        return LIVRE
    if (surplus + discricionario) / inflow >= limiar:
        return ESBANJADOR
    return VULNERAVEL


# Tese de resposta: faixa de tom e sentimento por segmento. O guard mede o texto
# do agente contra esta tabela (guard.verificar_tom). O sentimento é léxico, de -1 a 1.
PERFIS_DE_RESPOSTA = {
    VULNERAVEL: {
        "tom": "acolhedor e protetor",
        "sentimento": (0.0, 0.5),
        "exclamacoes_max": 0,
        "foco": "compromisso financeiro: renegociar antes de cortar essencial",
        "proibidos": ("novo empréstimo", "novo crédito", "aproveite", "urgente", "garantido", "sem risco"),
        "exigidos_um_de": ("vamos", "juntos", "passo", "organizar", "proteger"),
    },
    ESBANJADOR: {
        "tom": "direto e encorajador",
        "sentimento": (-0.2, 0.4),
        "exclamacoes_max": 1,
        "foco": "discricionário: nomear a categoria e o valor que devolvem a folga",
        "proibidos": ("irresponsável", "descontrole", "culpa", "garantido", "sem risco"),
        "exigidos_um_de": ("reduzir", "cortar", "ajustar", "meta", "limite"),
    },
    LIVRE: {
        "tom": "consultivo",
        "sentimento": (0.2, 0.7),
        "exclamacoes_max": 1,
        "foco": "excedente: reserva e investimento, sem promessa de retorno",
        "proibidos": ("rentabilidade garantida", "sem risco", "garantido", "lucro certo"),
        "exigidos_um_de": ("reserva", "investir", "aplicar", "planejar", "objetivo"),
    },
}
