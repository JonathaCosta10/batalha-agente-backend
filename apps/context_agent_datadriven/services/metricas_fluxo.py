"""
Métricas de fluxo, dívidas, T3, scores e Open Finance — implementação PURA da especificação de produto
colada pelo dono em 2026-09-27 (sem Django, sem I/O, sem BigQuery, sem modelo).

Este módulo NÃO substitui o T3 em produção (apps/context_agent_datadriven/pastas_raiz/estudos/i_agora/t3.py).
Ele existe para que a especificação seja executável e testável; as divergências entre a especificação e o
código atual estão registradas como `@unittest.expectedFailure` em tests/test_spec_*.py.

Toda escolha que a especificação deixava em aberto é uma constante com o marcador e o motivo. Em 2026-09-27
(09:28 BRT) o dono aceitou todas as recomendações (D-10/D-11/D-12 e demais): o marcador passou de
DECISAO_PENDENTE para "DECIDIDO 2026-09-27 (dono aceitou a recomendação)", sem mudar nenhum valor.
A lista completa segue em DECISOES_PENDENTES (nome mantido por compatibilidade; no fim do módulo); um teste
confere que cada item existe.

Unidades:
- valores em R$ como Decimal (entrada aceita int/float/str/Decimal; float passa por str() para não herdar
  o erro binário: 0.85 vira Decimal('0.85'), não 0.84999...);
- margem em PERCENTUAL (15 = 15 %); razões (Outflow/Inflow) em FRAÇÃO (0.85);
- anomes = inteiro AAAAMM (como `extrato_sintetico.anomes`).
"""

from __future__ import annotations

import statistics
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Mapping

# ---------------------------------------------------------------- rótulos

VULNERAVEL = "Vulnerável"
ESBANJADOR = "Esbanjador"
LIVRE = "Livre"
# Especificação §6 (Open Finance, futuro).
ESBANJADOR_RISCO_CONTROLADO = "Esbanjador de Risco Controlado"
NAO_MEDIDO = "NAO_MEDIDO"
# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (T3 sem segmento): a especificação define três perfis por condições que NÃO cobrem todos os
# casos (ex.: margem >= 15 % só nos 2 últimos meses, sem gasto variável alto). Em vez de forçar um perfil,
# devolvemos SEM_SEGMENTO. Alternativa: cair no perfil "mais próximo" (exige regra de distância).
SEM_SEGMENTO = "SEM_SEGMENTO"

MA_DIVIDA = "MA_DIVIDA"
BOA_DIVIDA = "BOA_DIVIDA"
FINANCIAMENTO_INCOMPATIVEL = "FINANCIAMENTO_INCOMPATIVEL"
FORA_DA_SPEC = "FORA_DA_SPEC"  # lançamento que a especificação não chama de dívida boa nem má

SEM_DEFICIT = "SEM_DEFICIT"
SAZONAL = "SAZONAL"
PONTUAL = "PONTUAL"
INSUSTENTAVEL = "INSUSTENTAVEL"

# ---------------------------------------------------------------- limiares da especificação (não pendentes)

# Especificação §3: margem < 15 % = Vulnerável; margem >= 15 % é condição de Livre.
# Mesmo valor que `t3.limiar_surplus` em desafio_itau/politica/operacional-v1.json (0.15); o teste de
# equivalência lê a política — este módulo não a importa para continuar puro.
LIMIAR_MARGEM_PCT = Decimal("15")
# Especificação §3: Livre exige margem >= 15 % "estável em >= 3 meses".
MESES_ESTAVEIS_LIVRE = 3
# Especificação §3: Livre exige "dívida cara < 10 %" (fração do Inflow).
LIMIAR_DIVIDA_CARA = Decimal("0.10")
# Especificação §2: déficit em >= 3 meses = insustentável.
MESES_DEFICIT_INSUSTENTAVEL = 3
DEZEMBRO = 12
# Especificação §6: patrimônio investido > R$ 50.000 (estritamente maior) e atraso > 15 dias (estritamente maior).
PATRIMONIO_RISCO_CONTROLADO = Decimal("50000")
ATRASO_MAX_DIAS = 15

# Especificação §4: pesos em pontos (somam 100).
PESOS_FLEXIBILITY = {"margem": Decimal("40"), "comprometimento": Decimal("30"), "estabilidade": Decimal("30")}
PESOS_BEHAVIOR = {"margem": Decimal("40"), "credito": Decimal("35"), "volatilidade": Decimal("25")}

# ---------------------------------------------------------------- DECISOES PENDENTES

# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (faixa do Esbanjador): "Outflow/Inflow entre >= 0,70 e 0,85". Lemos a faixa FECHADA nas duas
# pontas: 0,70 <= razão <= 0,85. Em 0,85 a margem é exatamente 15 %, que NÃO é Vulnerável (< 15 %), então a
# ponta fechada não cria conflito. Alternativa: [0,70; 0,85).
ESBANJADOR_RAZAO_MIN = Decimal("0.70")
ESBANJADOR_RAZAO_MAX = Decimal("0.85")
ESBANJADOR_RAZAO_MAX_INCLUSIVO = True

# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (Inflow médio/alto): a especificação não dá valor. Não inventamos um: o padrão é None e, sem
# limiar, o critério NÃO é avaliado — o resultado leva a pendência "inflow_medio_alto_nao_avaliado" e o critério
# é tratado como satisfeito. Quem tiver o limiar medido (ex.: mediana do Inflow da base, medida por outro agente)
# passa `inflow_medio_min` a classificar_t3_spec.
INFLOW_MEDIO_ALTO_MIN = None

# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (gasto discricionário alto): variável / Outflow >= 0,1593 = mediana da base medida
# (0.1593 · docs/estudo-i-agora/medicoes/2026-09-27/q_spec_diagnostico.json · 2026-09-27T09:17 BRT, job
# 2fed39aa). Ressalva: a mediana foi medida com a definição de discricionário daquela consulta, que pode ser mais
# larga que VARIAVEL_MACROS abaixo. Alternativa: 30 % do Inflow ("desejos" do 50-30-20).
DISCRICIONARIO_ALTO_FRACAO_OUTFLOW = Decimal("0.1593")

# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (Inflow = 0): sem Inflow não há margem (divisão por zero). A margem fica None (NAO_MEDIDO),
# nunca 0 nem -100 %. No T3, Inflow = 0 com Outflow > 0 tem Surplus < 0 => Vulnerável; Inflow = 0 e Outflow = 0
# (sem movimento) => NAO_MEDIDO. Nos scores, Inflow total = 0 => score None (NAO_MEDIDO).
INFLOW_ZERO_MARGEM = None

# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (precedência): um cliente pode cumprir condições de mais de um perfil. Ordem aplicada:
# Vulnerável > Esbanjador > Livre (o risco manda). Ex.: razão 0,80 com cheque especial ativo => Vulnerável.
PRECEDENCIA_T3 = (VULNERAVEL, ESBANJADOR, LIVRE)

# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (base do T3): o T3 é decidido sobre a JANELA agregada (soma dos meses), como o T3 atual usa
# a média da janela; a série mês a mês entra na estabilidade do Livre e no uso ativo de crédito.
# DECIDIDO 2026-09-27 (dono aceitou a recomendação) ("estável em >= 3 meses"): pelo menos 3 meses QUAISQUER da janela com margem >= 15 %, a
# mesma leitura da medição da base (q_spec_diagnostico.json, 09:17 BRT: "margem>=15% em >=3 dos 12 meses").
# Alternativa (True): os 3 meses mais recentes, consecutivos.
LIVRE_MESES_RECENTES_CONSECUTIVOS = False
# DECIDIDO 2026-09-27 (dono aceitou a recomendação) ("uso ativo" de cheque especial/juros): crédito emergencial em pelo menos um dos 3 meses
# mais recentes da janela. A medição da base usou os 12 meses.
MESES_USO_ATIVO = 3

# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (cheque especial): a base NÃO tem categoria de cheque especial (q_spec_diagnostico.json,
# 09:17 BRT). Proxy adotado: saldo_apos < 0 em algum lançamento do mês (327 de 1000 clientes em 12 meses, mesma
# fonte). A subcategoria "Cheque" (Outros gastos; 73 clientes em 12 meses) é pagamento em cheque, NÃO cheque
# especial: fica fora por padrão. Rótulos sintéticos "Cheque especial"/"Juros rotativos" (Open Finance futuro)
# também contam.
CHEQUE_ESPECIAL_PROXY_SALDO_NEGATIVO = True
CHEQUE_ESPECIAL_PROXY_MICRO_CHEQUE = False

# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (Fixo): "moradia, luz, água" mapeados às subcategorias reais de Casa (q02_categorias.json,
# medido 2026-09-27T03:48 BRT). Gás, internet, celular e seguro residencial ficam FORA por não estarem citados.
FIXO_SUBCATEGORIAS = {
    ("Casa", "Pagamento de aluguel"),   # moradia
    ("Casa", "Condominio"),             # moradia
    ("Casa", "IPTU"),                   # moradia
    ("Casa", "Energia eletrica"),       # luz
    ("Casa", "Agua e esgoto"),          # água
}
# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (Variável): "lazer, compras, restaurantes" = macros Lazer, Lojas e sites, Restaurantes.
# Delivery, Viagens, Assinaturas etc. (discricionário no t3.py atual) ficam FORA por não estarem citados.
# O "gasto discricionário" do Esbanjador é este Variável.
VARIAVEL_MACROS = {"Lazer", "Lojas e sites", "Restaurantes"}

# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (Juros pagos): a base não tem "juros rotativos" (q02_categorias.json, 2026-09-27T03:48 BRT).
# "Juros pagos" conta como MÁ DÍVIDA (dívida cara do Livre), mas NÃO como gatilho de "juros altos" do Vulnerável:
# atinge 695 de 1000 clientes (q02 e q_spec_diagnostico.json, 09:17 BRT) e, usado como gatilho OU, leva 97,8 %
# (309/316) do recorte N=316 a Vulnerável (q_spec_diagnostico.json, 09:17 BRT) — o gatilho deixaria de
# discriminar. classificar_t3_spec(juros_pagos_gatilho=True) liga a leitura alternativa.
JUROS_PAGOS_E_CREDITO_EMERGENCIAL = False
# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (tarifas e multas): "Outras tarifas financeiras", "Anuidade e pacote de servico" (tarifas) e
# "Multa por atraso" contam como má dívida / dívida cara (lista de dívida cara de q_spec_diagnostico.json), mas NÃO
# como crédito emergencial. A especificação cita só "tarifas": a multa é extensão nossa.
TARIFAS_SUBCATEGORIAS = {("Produtos financeiros", "Outras tarifas financeiras"),
                         ("Produtos financeiros", "Anuidade e pacote de servico")}
MULTA_SUBCATEGORIAS = {("Outros gastos", "Multa por atraso")}
# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (financiamento compatível): parcela do financiamento imobiliário <= 30 % do Inflow do mês.
# Os 30 % são o costume de mercado de comprometimento de renda com habitação, não medida nem norma citada.
# Incompatível => FINANCIAMENTO_INCOMPATIVEL (nem boa nem má: a especificação não diz).
FINANCIAMENTO_COMPATIVEL_MAX_FRACAO = Decimal("0.30")
FINANCIAMENTO_IMOVEL = ("Emprestimos e financiamentos", "Financiamento de imovel")
# DECIDIDO 2026-09-27 (dono aceitou a recomendação) ("parcelas" do Flexibility): as quatro subcategorias de financiamento da base
# (q_spec_diagnostico.json, 09:17 BRT): Financiamento de imovel, Emprestimos, Outros emprestimos, Consorcio.
PARCELAS_SUBCATEGORIAS = {
    ("Emprestimos e financiamentos", "Financiamento de imovel"),
    ("Emprestimos e financiamentos", "Emprestimos"),
    ("Emprestimos e financiamentos", "Outros emprestimos"),
    ("Produtos financeiros", "Consorcio"),
}

# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (normalização dos scores para 0..1):
#  - margem: margem_pct / 100, recortada em [0, 1] (margem <= 0 => 0). LINEAR até 100 % de propósito: um corte
#    em 15 % ou 20 % satura o score — a medição da base com clip(margem/0,15) deu média EXATAMENTE 100,0 no
#    Esbanjador e no Livre (q_spec_diagnostico.json, 09:17 BRT), e o score deixa de separar margem 20 % de 60 %;
#  - comprometimento (Flexibility): 1 - (fixos + parcelas) / Inflow, recortado em [0, 1];
#  - estabilidade (Flexibility): meses com Surplus > 0 / meses da janela;
#  - crédito (Behavior): penalidade = fração dos meses com crédito emergencial > 0;
#  - volatilidade (Behavior): penalidade = coeficiente de variação amostral do Inflow mensal, recortado em
#    [0, 1] (mesma medida de `cv_inflow` em populacao_t3.sql); com < 2 meses não se mede (penalidade 0 e pendência).
MARGEM_TETO_PCT = Decimal("100")

# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (Open Finance "zera o componente de crédito"): lido como a parcela de crédito do Behavior
# passar a valer 0 pontos, isto é, penalidade de crédito MÁXIMA (35). A leitura oposta (penalidade 0) premiaria
# o atraso.
ZERAR_CREDITO_E_PENALIDADE_MAXIMA = True

# DECIDIDO 2026-09-27 (dono aceitou a recomendação) (dezembro sem janeiro-dezembro completo): a avaliação longitudinal roda com os meses que houver
# e marca completo=False quando não há os 12 meses de um ano.

DECISOES_PENDENTES = (
    "ESBANJADOR_RAZAO_MAX_INCLUSIVO",
    "INFLOW_MEDIO_ALTO_MIN",
    "DISCRICIONARIO_ALTO_FRACAO_OUTFLOW",
    "INFLOW_ZERO_MARGEM",
    "PRECEDENCIA_T3",
    "SEM_SEGMENTO",
    "LIVRE_MESES_RECENTES_CONSECUTIVOS",
    "MESES_USO_ATIVO",
    "CHEQUE_ESPECIAL_PROXY_SALDO_NEGATIVO",
    "CHEQUE_ESPECIAL_PROXY_MICRO_CHEQUE",
    "FIXO_SUBCATEGORIAS",
    "VARIAVEL_MACROS",
    "JUROS_PAGOS_E_CREDITO_EMERGENCIAL",
    "TARIFAS_SUBCATEGORIAS",
    "MULTA_SUBCATEGORIAS",
    "FINANCIAMENTO_COMPATIVEL_MAX_FRACAO",
    "PARCELAS_SUBCATEGORIAS",
    "MARGEM_TETO_PCT",
    "ZERAR_CREDITO_E_PENALIDADE_MAXIMA",
)

# ---------------------------------------------------------------- tom por perfil (especificação §5)

# Eixos exigidos: cada eixo é satisfeito se o texto normalizado (minúsculo, sem acento) contém UM dos radicais.
# Proibidos: rótulo interno ou julgamento. Radicais escolhidos para não casar por acaso (ex.: "estabiliz", e não
# "equilibr", que aparece em "entradas e saídas ficaram equilibradas").
TOM_SPEC = {
    VULNERAVEL: {
        "tom": "acolhedor, não julgador",
        "eixos": {
            "acolhedor": ("acolh",),
            "estabilizar": ("estabiliz",),
            "cortar_superfluos": ("superflu",),
            "eliminar_cheque_especial": ("cheque especial",),
        },
        "proibidos": ("vulneravel", "irresponsavel", "descontrol", "culpa", "vergonha"),
    },
    ESBANJADOR: {
        "tom": "provocativo",
        "eixos": {
            "provocativo": ("provoc",),
            "trade_offs": ("trade-off", "trade off", "abrir mao", "em vez de", "troca", "custo de oportunidade"),
            "impacto_futuro": ("futuro", "longo prazo", "daqui a"),
        },
        "proibidos": ("esbanjador", "voce e gastador", "irresponsavel", "culpa"),
    },
    LIVRE: {
        "tom": "consultivo",
        "eixos": {
            "consultivo": ("consult",),
            "investimento": ("invest",),
            "reserva": ("reserva",),
            "patrimonio": ("patrimon",),
        },
        "proibidos": ("garantid", "sem risco", "lucro certo"),
    },
}


def normalizar(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(texto).lower()) if unicodedata.category(c) != "Mn")


def avaliar_tom(texto: str, segmento: str) -> dict:
    """Eixos presentes/ausentes e proibidos encontrados num texto, contra TOM_SPEC[segmento]."""
    spec = TOM_SPEC[segmento]
    norm = normalizar(texto)
    faltam = [eixo for eixo, radicais in spec["eixos"].items() if not any(r in norm for r in radicais)]
    proibidos = [p for p in spec["proibidos"] if p in norm]
    return {"faltam": faltam, "proibidos": proibidos, "aprovado": not faltam and not proibidos}


# ---------------------------------------------------------------- utilidades

def _d(valor) -> Decimal:
    if valor is None:
        raise ValueError("valor ausente não vira zero")
    if isinstance(valor, bool):
        raise ValueError("booleano não é valor")
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def _campo(obj, nome, padrao=None):
    if isinstance(obj, Mapping):
        return obj.get(nome, padrao)
    return getattr(obj, nome, padrao)


def _recorte(x: Decimal) -> Decimal:
    return min(Decimal(1), max(Decimal(0), x))


_ENTRADA = {True, "V", "E", "TRUE", "ENTRADA"}
_SAIDA = {False, "F", "S", "FALSE", "SAIDA"}


def eh_entrada(tipo) -> bool:
    """V/True/E = entrada; F/False/S = saída. Qualquer outro valor é erro (não vira saída por omissão)."""
    chave = tipo.strip().upper() if isinstance(tipo, str) else tipo
    if isinstance(chave, bool) or isinstance(chave, str):
        if chave in _ENTRADA:
            return True
        if chave in _SAIDA:
            return False
    raise ValueError(f"tipo de lançamento desconhecido: {tipo!r}")


# ---------------------------------------------------------------- §1 métricas por cliente × mês

@dataclass(frozen=True)
class Lancamento:
    id_usuario: str
    anomes: int
    tipo: object          # True/'V'/'E' entrada; False/'F'/'S' saída
    valor: object
    macro: str = ""
    micro: str = ""
    saldo_apos: object = None  # saldo da conta depois do lançamento; < 0 é o proxy de cheque especial


@dataclass(frozen=True)
class MetricasMes:
    id_usuario: str
    anomes: int
    inflow: Decimal
    outflow: Decimal
    surplus: Decimal
    margem_pct: Decimal | None
    fixo: Decimal = Decimal(0)
    variavel: Decimal = Decimal(0)
    parcelas: Decimal = Decimal(0)
    ma_divida: Decimal = Decimal(0)
    credito_emergencial: Decimal = Decimal(0)
    cheque_especial: Decimal = Decimal(0)
    juros_pagos: Decimal = Decimal(0)
    financiamento_imovel: Decimal = Decimal(0)
    uso_cheque_especial: bool = False  # saldo_apos < 0 no mês (proxy) ou valor em cheque especial


def margem_pct(inflow, outflow) -> Decimal | None:
    """Surplus / Inflow × 100. Inflow = 0 => None (NAO_MEDIDO), ver INFLOW_ZERO_MARGEM."""
    inflow, outflow = _d(inflow), _d(outflow)
    if inflow == 0:
        return INFLOW_ZERO_MARGEM
    return (inflow - outflow) / inflow * 100


_EMERGENCIAL = ("cheque_especial", "juros_rotativos")


def _subtipo_ma(macro: str, micro: str) -> str | None:
    """cheque_especial | juros_rotativos | juros_pagos | tarifas | multas | None."""
    m = normalizar(micro)
    if "cheque especial" in m or (CHEQUE_ESPECIAL_PROXY_MICRO_CHEQUE and m == "cheque"):
        return "cheque_especial"
    if "rotativo" in m:
        return "juros_rotativos"
    if (macro, micro) in TARIFAS_SUBCATEGORIAS or "tarifa" in m:
        return "tarifas"
    if (macro, micro) in MULTA_SUBCATEGORIAS:
        return "multas"
    if m == "juros pagos":
        return "juros_pagos"
    return None


def classificar_divida(macro: str, micro: str, valor_mensal=None, inflow_mensal=None) -> dict:
    """§2: má dívida (cheque especial, juros rotativos, tarifas) × boa dívida (financiamento imobiliário
    compatível com o Inflow). "Cheque" (Outros gastos) não é cheque especial (CHEQUE_ESPECIAL_PROXY_MICRO_CHEQUE)."""
    sub = _subtipo_ma(macro, micro)
    if sub:
        return {"classe": MA_DIVIDA, "subtipo": sub, "credito_emergencial": sub in _EMERGENCIAL}
    if (macro, micro) == FINANCIAMENTO_IMOVEL:
        if valor_mensal is None or inflow_mensal is None:
            return {"classe": NAO_MEDIDO, "subtipo": "financiamento_imovel", "credito_emergencial": False,
                    "motivo": "sem parcela ou sem Inflow não se mede a compatibilidade"}
        inflow = _d(inflow_mensal)
        compativel = inflow > 0 and _d(valor_mensal) / inflow <= FINANCIAMENTO_COMPATIVEL_MAX_FRACAO
        return {"classe": BOA_DIVIDA if compativel else FINANCIAMENTO_INCOMPATIVEL,
                "subtipo": "financiamento_imovel", "credito_emergencial": False}
    return {"classe": FORA_DA_SPEC, "subtipo": None, "credito_emergencial": False}


def metricas_mes(lancamentos: Iterable) -> dict:
    """Lançamentos (Lancamento ou dict) -> {(id_usuario, anomes): MetricasMes}. Valor em módulo, como
    ABS(vlr) em populacao_t3.sql."""
    acum: dict = {}
    for l in lancamentos:
        chave = (_campo(l, "id_usuario"), int(_campo(l, "anomes")))
        a = acum.setdefault(chave, {**{k: Decimal(0) for k in (
            "inflow", "outflow", "fixo", "variavel", "parcelas", "ma_divida", "credito_emergencial",
            "cheque_especial", "juros_pagos", "financiamento_imovel")}, "uso_cheque_especial": False})
        valor = abs(_d(_campo(l, "valor")))
        saldo = _campo(l, "saldo_apos")
        if CHEQUE_ESPECIAL_PROXY_SALDO_NEGATIVO and saldo is not None and _d(saldo) < 0:
            a["uso_cheque_especial"] = True
        if eh_entrada(_campo(l, "tipo")):
            a["inflow"] += valor
            continue
        a["outflow"] += valor
        macro, micro = _campo(l, "macro", "") or "", _campo(l, "micro", "") or ""
        if (macro, micro) in FIXO_SUBCATEGORIAS:
            a["fixo"] += valor
        if macro in VARIAVEL_MACROS:
            a["variavel"] += valor
        if (macro, micro) in PARCELAS_SUBCATEGORIAS:
            a["parcelas"] += valor
        if (macro, micro) == FINANCIAMENTO_IMOVEL:
            a["financiamento_imovel"] += valor
        sub = _subtipo_ma(macro, micro)
        if sub:
            a["ma_divida"] += valor
            if sub in _EMERGENCIAL:
                a["credito_emergencial"] += valor
            if sub == "cheque_especial":
                a["cheque_especial"] += valor
                a["uso_cheque_especial"] = True
            if sub == "juros_pagos":
                a["juros_pagos"] += valor
    return {
        (u, am): MetricasMes(id_usuario=u, anomes=am, surplus=a["inflow"] - a["outflow"],
                             margem_pct=margem_pct(a["inflow"], a["outflow"]), **a)
        for (u, am), a in sorted(acum.items(), key=lambda kv: (str(kv[0][0]), kv[0][1]))
    }


# ---------------------------------------------------------------- §2 avaliação longitudinal

def avaliar_longitudinal(meses) -> dict:
    """`meses`: {anomes: surplus} ou lista de MetricasMes/dicts com anomes e surplus.
    Déficit = Surplus < 0 (zero não é déficit). Só dezembro => SAZONAL; >= 3 meses => INSUSTENTAVEL."""
    if isinstance(meses, Mapping):
        serie = {int(k): _d(v) for k, v in meses.items()}
    else:
        serie = {int(_campo(m, "anomes")): _d(_campo(m, "surplus")) for m in meses}
    if not serie:
        return {"classe": NAO_MEDIDO, "meses_deficit": [], "completo": False}
    deficit = sorted(am for am, s in serie.items() if s < 0)
    anos = {am // 100 for am in serie}
    completo = any(all(a * 100 + m in serie for m in range(1, 13)) for a in anos)
    if not deficit:
        classe = SEM_DEFICIT
    elif len(deficit) >= MESES_DEFICIT_INSUSTENTAVEL:
        classe = INSUSTENTAVEL
    elif all(am % 100 == DEZEMBRO for am in deficit):
        classe = SAZONAL
    else:
        classe = PONTUAL
    return {"classe": classe, "meses_deficit": deficit, "completo": completo}


# ---------------------------------------------------------------- agregação da janela

def _serie(meses) -> list:
    lista = list(meses.values()) if isinstance(meses, Mapping) else list(meses)
    return sorted(lista, key=lambda m: int(_campo(m, "anomes")))


def _soma(serie, nome) -> Decimal:
    return sum((_d(_campo(m, nome, 0) or 0) for m in serie), Decimal(0))


def _margem_mes(m) -> Decimal | None:
    return margem_pct(_campo(m, "inflow"), _campo(m, "outflow"))


# ---------------------------------------------------------------- §3 T3

def _usa_credito(m, juros_pagos_gatilho: bool) -> bool:
    return (bool(_campo(m, "uso_cheque_especial", False))
            or _d(_campo(m, "credito_emergencial", 0) or 0) > 0
            or (juros_pagos_gatilho and _d(_campo(m, "juros_pagos", 0) or 0) > 0))


def classificar_t3_spec(meses, inflow_medio_min=INFLOW_MEDIO_ALTO_MIN,
                        juros_pagos_gatilho: bool = JUROS_PAGOS_E_CREDITO_EMERGENCIAL) -> dict:
    """Segmento T3 pela especificação. `meses`: lista (ou dict) de MetricasMes ou dicts com anomes, inflow,
    outflow e, opcionalmente, variavel, credito_emergencial, uso_cheque_especial, juros_pagos, ma_divida."""
    serie = _serie(meses)
    pendencias = []
    if not serie:
        return {"segmento": NAO_MEDIDO, "motivos": ["janela sem meses"], "pendencias": pendencias}
    inflow, outflow = _soma(serie, "inflow"), _soma(serie, "outflow")
    if inflow == 0 and outflow == 0:
        return {"segmento": NAO_MEDIDO, "motivos": ["sem movimento na janela"], "pendencias": pendencias}
    surplus = inflow - outflow
    margem = margem_pct(inflow, outflow)
    recentes = serie[-MESES_USO_ATIVO:]
    credito_ativo = any(_usa_credito(m, juros_pagos_gatilho) for m in recentes)

    candidatos = {}
    motivos_v = []
    if surplus < 0:
        motivos_v.append("surplus < 0")
    if margem is not None and margem < LIMIAR_MARGEM_PCT:
        motivos_v.append("margem < 15 %")
    if credito_ativo:
        motivos_v.append("uso ativo de cheque especial ou juros altos")
    if motivos_v:
        candidatos[VULNERAVEL] = motivos_v

    if inflow > 0:
        razao = outflow / inflow
        teto_ok = razao <= ESBANJADOR_RAZAO_MAX if ESBANJADOR_RAZAO_MAX_INCLUSIVO else razao < ESBANJADOR_RAZAO_MAX
        na_faixa = ESBANJADOR_RAZAO_MIN <= razao and teto_ok
        discricionario_alto = outflow > 0 and _soma(serie, "variavel") / outflow >= DISCRICIONARIO_ALTO_FRACAO_OUTFLOW
        sem_cheque = not any(bool(_campo(m, "uso_cheque_especial", False)) for m in serie) \
            and _soma(serie, "cheque_especial") == 0
        if inflow_medio_min is None:
            inflow_ok = True
            pendencias.append("inflow_medio_alto_nao_avaliado")
        else:
            inflow_ok = inflow / len(serie) >= _d(inflow_medio_min)
        if na_faixa and discricionario_alto and sem_cheque and inflow_ok:
            candidatos[ESBANJADOR] = [f"Outflow/Inflow = {razao:.4f} na faixa", "variável alto", "sem cheque especial"]

        ultimos = serie[-MESES_ESTAVEIS_LIVRE:] if LIVRE_MESES_RECENTES_CONSECUTIVOS else serie
        estaveis = [m for m in ultimos if (_margem_mes(m) is not None and _margem_mes(m) >= LIMIAR_MARGEM_PCT)]
        estavel = len(estaveis) >= MESES_ESTAVEIS_LIVRE
        sem_emergencial = not any(_usa_credito(m, juros_pagos_gatilho) for m in serie)
        divida_cara_ok = _soma(serie, "ma_divida") / inflow < LIMIAR_DIVIDA_CARA
        if margem >= LIMIAR_MARGEM_PCT and estavel and sem_emergencial and divida_cara_ok:
            candidatos[LIVRE] = ["margem >= 15 % estável", "sem crédito emergencial", "dívida cara < 10 %"]

    for seg in PRECEDENCIA_T3:
        if seg in candidatos:
            return {"segmento": seg, "motivos": candidatos[seg], "candidatos": sorted(candidatos),
                    "pendencias": pendencias}
    return {"segmento": SEM_SEGMENTO, "motivos": ["nenhuma condição da especificação fechou"], "candidatos": [],
            "pendencias": pendencias}


# ---------------------------------------------------------------- §4 scores

def _componente_margem(margem: Decimal | None) -> Decimal:
    if margem is None:
        return Decimal(0)
    return _recorte(margem / MARGEM_TETO_PCT)


def flexibility_score(meses) -> dict:
    """40 % margem + 30 % comprometimento com fixos e parcelas + 30 % estabilidade (meses com superávit)."""
    serie = _serie(meses)
    inflow = _soma(serie, "inflow")
    if not serie or inflow == 0:
        return {"score": None, "estado": NAO_MEDIDO, "motivo": "Inflow total = 0: sem base para o score"}
    outflow = _soma(serie, "outflow")
    comp = {
        "margem": _componente_margem(margem_pct(inflow, outflow)),
        "comprometimento": _recorte(1 - (_soma(serie, "fixo") + _soma(serie, "parcelas")) / inflow),
        "estabilidade": Decimal(sum(1 for m in serie if _d(_campo(m, "inflow")) - _d(_campo(m, "outflow")) > 0))
        / len(serie),
    }
    score = sum(PESOS_FLEXIBILITY[k] * v for k, v in comp.items())
    return {"score": score, "estado": "MEDIDO", "componentes": comp}


def behavior_score(meses, zerar_credito: bool = False) -> dict:
    """100 − penalidades: margem 40 %, crédito/cheque especial 35 %, volatilidade 25 %."""
    serie = _serie(meses)
    inflow = _soma(serie, "inflow")
    if not serie or inflow == 0:
        return {"score": None, "estado": NAO_MEDIDO, "motivo": "Inflow total = 0: sem base para o score"}
    pendencias = []
    outflow = _soma(serie, "outflow")
    pen = {"margem": 1 - _componente_margem(margem_pct(inflow, outflow))}
    if zerar_credito and ZERAR_CREDITO_E_PENALIDADE_MAXIMA:
        pen["credito"] = Decimal(1)
    else:
        pen["credito"] = Decimal(sum(1 for m in serie if _usa_credito(m, JUROS_PAGOS_E_CREDITO_EMERGENCIAL))) / len(serie)
    entradas = [_d(_campo(m, "inflow")) for m in serie]
    if len(entradas) < 2:
        pen["volatilidade"] = Decimal(0)
        pendencias.append("volatilidade_nao_medida_menos_de_2_meses")
    else:
        media = sum(entradas) / len(entradas)
        pen["volatilidade"] = _recorte(Decimal(str(statistics.stdev(entradas))) / media) if media > 0 else Decimal(1)
    score = Decimal(100) - sum(PESOS_BEHAVIOR[k] * v for k, v in pen.items())
    return {"score": score, "estado": "MEDIDO", "penalidades": pen, "pendencias": pendencias}


# ---------------------------------------------------------------- §6 Open Finance

@dataclass(frozen=True)
class DadosOpenFinance:
    patrimonio_investido: object = None      # R$; None = não medido
    atraso_fatura_externa_dias: object = None  # dias; None = não medido
    extras: dict = field(default_factory=dict)


def ajustar_open_finance(segmento: str, surplus, dados) -> dict:
    """Surplus < 0 com patrimônio > R$ 50.000 => Esbanjador de Risco Controlado; atraso > 15 dias em fatura
    externa => zera o componente de crédito do score. Dado ausente não muda nada e é dito."""
    patrimonio = _campo(dados, "patrimonio_investido")
    atraso = _campo(dados, "atraso_fatura_externa_dias")
    nao_medidos = [n for n, v in (("patrimonio_investido", patrimonio), ("atraso_fatura_externa_dias", atraso))
                   if v is None]
    novo = segmento
    if surplus is not None and patrimonio is not None and _d(surplus) < 0 and _d(patrimonio) > PATRIMONIO_RISCO_CONTROLADO:
        novo = ESBANJADOR_RISCO_CONTROLADO
    zerar = atraso is not None and _d(atraso) > ATRASO_MAX_DIAS
    return {"segmento": novo, "zerar_componente_credito": zerar, "nao_medidos": nao_medidos}
