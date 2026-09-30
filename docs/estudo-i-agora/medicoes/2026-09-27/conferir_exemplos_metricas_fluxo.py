"""Confere os exemplos calculados a mão contra metricas_fluxo.py (sem editar o módulo)."""
import importlib.util, sys
from decimal import Decimal as D

CAMINHO = r"apps\context_agent_datadriven\services\metricas_fluxo.py"
spec = importlib.util.spec_from_file_location("metricas_fluxo", CAMINHO)
mf = importlib.util.module_from_spec(spec)
sys.modules["metricas_fluxo"] = mf
spec.loader.exec_module(mf)

falhas = []
def conf(nome, obtido, esperado):
    ok = obtido == esperado
    print(("OK   " if ok else "FALHA"), nome, "| obtido:", obtido, "| esperado:", esperado)
    if not ok:
        falhas.append(nome)

# 1. Métricas por cliente x mês
L = mf.Lancamento
lanc = [
    L("u1", 202501, "E", 5000, "Salarios e bonificacoes", "Salario CLT"),
    L("u1", 202501, "S", 1500, "Casa", "Pagamento de aluguel"),
    L("u1", 202501, "S", 800, "Lazer", "Cinema"),
    L("u1", 202501, "S", 50, "Produtos financeiros", "Juros pagos"),
    L("u1", 202501, "S", -1000, "Emprestimos e financiamentos", "Financiamento de imovel"),
]
m = mf.metricas_mes(lanc)[("u1", 202501)]
conf("1a inflow", m.inflow, D(5000))
conf("1b outflow (valor em módulo)", m.outflow, D(3350))
conf("1c surplus", m.surplus, D(1650))
conf("1d margem_pct", m.margem_pct, D(33))
conf("1e fixo", m.fixo, D(1500))
conf("1f variavel", m.variavel, D(800))
conf("1g parcelas", m.parcelas, D(1000))
conf("1h ma_divida (juros pagos)", m.ma_divida, D(50))
conf("1i credito_emergencial", m.credito_emergencial, D(0))
conf("1j margem exatamente 15", mf.margem_pct(1000, 850), D(15))
conf("1k inflow zero -> None", mf.margem_pct(0, 300), None)

# 2. Dívidas
cd = mf.classificar_divida
conf("2a financiamento 1500/5000 = 30 % -> boa", cd("Emprestimos e financiamentos", "Financiamento de imovel", 1500, 5000)["classe"], mf.BOA_DIVIDA)
conf("2b financiamento 1501/5000 -> incompatível", cd("Emprestimos e financiamentos", "Financiamento de imovel", 1501, 5000)["classe"], mf.FINANCIAMENTO_INCOMPATIVEL)
conf("2c financiamento sem inflow -> NAO_MEDIDO", cd("Emprestimos e financiamentos", "Financiamento de imovel", 1500, None)["classe"], mf.NAO_MEDIDO)
r = cd("Produtos financeiros", "Juros pagos")
conf("2d juros pagos = má dívida, não emergencial", (r["classe"], r["credito_emergencial"]), (mf.MA_DIVIDA, False))
r = cd("Sintetico", "Cheque especial")
conf("2e cheque especial = má dívida emergencial", (r["classe"], r["credito_emergencial"]), (mf.MA_DIVIDA, True))
conf("2f 'Cheque' (Outros gastos) fora da spec", cd("Outros gastos", "Cheque")["classe"], mf.FORA_DA_SPEC)
conf("2g multa = má dívida", cd("Outros gastos", "Multa por atraso")["subtipo"], "multas")

# 3. Longitudinal
ano = {202500 + i: D(100) for i in range(1, 13)}
s = dict(ano); s[202512] = D(-100)
r = mf.avaliar_longitudinal(s)
conf("3a só dezembro -> SAZONAL, completo", (r["classe"], r["completo"]), (mf.SAZONAL, True))
s = dict(ano); s[202503] = D(-1); s[202512] = D(-1)
conf("3b março + dezembro -> PONTUAL", mf.avaliar_longitudinal(s)["classe"], mf.PONTUAL)
s = dict(ano); s[202510] = D(-1); s[202511] = D(-1); s[202512] = D(-1)
conf("3c três meses (com dezembro) -> INSUSTENTAVEL", mf.avaliar_longitudinal(s)["classe"], mf.INSUSTENTAVEL)
s = dict(ano); s[202506] = D(0)
conf("3d surplus 0 não é déficit", mf.avaliar_longitudinal(s)["classe"], mf.SEM_DEFICIT)
r = mf.avaliar_longitudinal({202511: D(-5), 202512: D(10)})
conf("3e janela incompleta", (r["classe"], r["completo"]), (mf.PONTUAL, False))

# 4. T3 da especificação
def mes(am, i, o, var=0, cheque=False, ma=0):
    return {"anomes": am, "inflow": D(i), "outflow": D(o), "variavel": D(var), "uso_cheque_especial": cheque,
            "ma_divida": D(ma)}
t3 = mf.classificar_t3_spec
r = t3([mes(202509, 1000, 900), mes(202510, 1000, 900), mes(202511, 1000, 900)])
conf("4a margem 10 % -> Vulnerável", r["segmento"], mf.VULNERAVEL)
r = t3([mes(202509, 1000, 800, 200), mes(202510, 1000, 800, 200), mes(202511, 1000, 800, 200)])
conf("4b razão 0,80 e variável 25 % -> Esbanjador (Livre também candidato)", (r["segmento"], r["candidatos"], r["pendencias"]),
     (mf.ESBANJADOR, [mf.ESBANJADOR, mf.LIVRE], ["inflow_medio_alto_nao_avaliado"]))
r = t3([mes(202509, 1000, 600, 50), mes(202510, 1000, 600, 50), mes(202511, 1000, 600, 50)])
conf("4c razão 0,60 margem 40 % -> Livre", r["segmento"], mf.LIVRE)
r = t3([mes(202509, 1000, 1000), mes(202510, 1000, 500), mes(202511, 1000, 500)])
conf("4d margem 33,3 % mas só 2 meses estáveis e razão 0,667 -> SEM_SEGMENTO", r["segmento"], mf.SEM_SEGMENTO)
r = t3([mes(202509, 1000, 800, 200), mes(202510, 1000, 800, 200), mes(202511, 1000, 800, 200, cheque=True)])
conf("4e razão 0,80 com cheque especial no mês recente -> Vulnerável", (r["segmento"], r["candidatos"]), (mf.VULNERAVEL, [mf.VULNERAVEL]))
r = t3([mes(202509, 1000, 850, 200), mes(202510, 1000, 850, 200), mes(202511, 1000, 850, 200)])
conf("4f razão 0,85 (ponta fechada), margem 15 % -> Esbanjador", r["segmento"], mf.ESBANJADOR)
r = t3([mes(202509, 1000, 600, 50, ma=40), mes(202510, 1000, 600, 50, ma=40), mes(202511, 1000, 600, 50, ma=40)])
conf("4g dívida cara 120/3000 = 4 % -> Livre", r["segmento"], mf.LIVRE)
r = t3([mes(202509, 1000, 600, 50, ma=100), mes(202510, 1000, 600, 50, ma=100), mes(202511, 1000, 600, 50, ma=100)])
conf("4h dívida cara 300/3000 = 10 % (não < 10 %) -> SEM_SEGMENTO", r["segmento"], mf.SEM_SEGMENTO)
r = t3([mes(202511, 0, 0)])
conf("4i sem movimento -> NAO_MEDIDO", r["segmento"], mf.NAO_MEDIDO)
r = t3([mes(202511, 0, 300)])
conf("4j inflow 0 com saída -> Vulnerável", r["segmento"], mf.VULNERAVEL)

# 5. Scores
def mes5(am, i, o, fixo=300, parc=100, cheque=False):
    return {"anomes": am, "inflow": D(i), "outflow": D(o), "fixo": D(fixo), "parcelas": D(parc), "uso_cheque_especial": cheque}
serie = [mes5(202509, 800, 640), mes5(202510, 1000, 800), mes5(202511, 1200, 960)]
f = mf.flexibility_score(serie)
conf("5a Flexibility = 8 + 18 + 30 = 56", f["score"], D(56))
b = mf.behavior_score(serie)
conf("5b Behavior = 100 - 32 - 0 - 5 = 63", b["score"], D(63))
serie_c = [mes5(202509, 800, 640, cheque=True), mes5(202510, 1000, 800), mes5(202511, 1200, 960)]
b = mf.behavior_score(serie_c)
conf("5c Behavior com cheque em 1 de 3 meses = 51,33", round(b["score"], 2), D("51.33"))
b = mf.behavior_score(serie, zerar_credito=True)
conf("5d Behavior com crédito zerado (Open Finance) = 28", b["score"], D(28))
s20 = [mes5(202511, 1000, 800, 0, 0)]
s60 = [mes5(202511, 1000, 400, 0, 0)]
conf("5e margem 20 % -> componente 0,2 ; 60 % -> 0,6 (sem saturação)",
     (mf.flexibility_score(s20)["componentes"]["margem"], mf.flexibility_score(s60)["componentes"]["margem"]), (D("0.2"), D("0.6")))
b1 = mf.behavior_score(s20)
conf("5f um mês só: volatilidade não medida", b1["pendencias"], ["volatilidade_nao_medida_menos_de_2_meses"])
conf("5g inflow zero -> score None", mf.flexibility_score([mes5(202511, 0, 100)])["score"], None)

# 6. Open Finance
r = mf.ajustar_open_finance(mf.VULNERAVEL, -100, {"patrimonio_investido": "50000.01", "atraso_fatura_externa_dias": 16})
conf("6a patrimônio 50.000,01 e atraso 16 d", (r["segmento"], r["zerar_componente_credito"]), (mf.ESBANJADOR_RISCO_CONTROLADO, True))
r = mf.ajustar_open_finance(mf.VULNERAVEL, -100, {"patrimonio_investido": 50000, "atraso_fatura_externa_dias": 15})
conf("6b patrimônio 50.000 e atraso 15 d (fronteiras não disparam)", (r["segmento"], r["zerar_componente_credito"]), (mf.VULNERAVEL, False))
r = mf.ajustar_open_finance(mf.LIVRE, 500, {"patrimonio_investido": 90000})
conf("6c surplus positivo não muda; atraso ausente é declarado", (r["segmento"], r["nao_medidos"]), (mf.LIVRE, ["atraso_fatura_externa_dias"]))

print("DECISOES_PENDENTES:", len(mf.DECISOES_PENDENTES))
print("TOTAL FALHAS:", len(falhas), falhas)
