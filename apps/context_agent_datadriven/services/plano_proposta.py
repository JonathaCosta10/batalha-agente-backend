"""
Proposta de compromissos de janeiro a partir da modelagem do estudo i.agora — não da fórmula do front.

Regra `corte_seguro_ate_surplus_15` (cada passo cita a fonte no estudo):
  1. Perfil T3 do usuário (usuario_real.perfil): inflow, surplus e segmento, médias mensais da janela.
  2. Necessário para chegar a Livre (t3.LIMIAR_SURPLUS = 15 %): max(0, 0,15 × inflow − surplus).
  3. Candidatas: subcategorias (nom_cate_micro, grafia da tabela) das macros do grupo
     discricionário (t3.MAPA_GRUPOS). Essencial e compromisso financeiro nunca entram.
  4. Margem de corte seguro (consultas.margem_de_corte_seguro / classificar_essencialidade, pela macro):
     Nível 1 corta 100 % da média mensal; Nível 2 (restaurante, cuidados, transporte) corta 50 %.
  5. Guloso: maior margem primeiro, corte = min(margem, o que ainda falta), até MAX_COMPROMISSOS.
     meta = gasto_atual − corte. Subcategoria sem gasto na janela não entra.
  6. Livre (necessário = 0): nenhum corte; reserva = min(surplus, 20 % do inflow) — o "20" do 50-30-20.
  7. Se a soma das margens não cobre o necessário: estado CORTE_INSUFICIENTE (tese Vulnerável:
     renegociar o compromisso financeiro antes de cortar essencial).
"""

import time
from datetime import date

from ..pastas_raiz.estudos.i_agora import consultas, t3
from . import usuario_real

REGRA = "corte_seguro_ate_surplus_15"
MAX_COMPROMISSOS = 3
PCT_RESERVA_50_30_20 = 0.20
PERCENTUAL_POR_NIVEL = {consultas.NIVEL_1: 1.0, consultas.NIVEL_2: 0.5, consultas.NIVEL_3: 0.0}

SQL_SUBCATEGORIAS = """
, meses AS (SELECT COUNT(DISTINCT anomes) AS n FROM mov)
SELECT
  macro,
  micro AS subcategoria,
  COUNT(*) AS lancamentos,
  ROUND(SUM(valor), 2) AS total,
  ROUND(SAFE_DIVIDE(SUM(valor), (SELECT n FROM meses)), 2) AS gasto_mensal,
  (SELECT n FROM meses) AS meses,
  (SELECT MIN(anomes) FROM mov) AS base_inicio,
  (SELECT MAX(anomes) FROM mov) AS base_fim
FROM mov
WHERE tipo = 'S' AND grupo = 'discricionario'
GROUP BY macro, micro
HAVING SUM(valor) > 0
ORDER BY total DESC
"""

# Gasto discricionário do mês da linha de corte, do dia 1 até a data de corte (inclusive).
# Não entra na média: é o "até agora" de dezembro, mostrado ao lado da meta.
SQL_ATE_CORTE = """
WITH {{GRUPOS}}
SELECT
  e.nom_cate_macro AS macro,
  IFNULL(e.nom_cate_micro, '') AS subcategoria,
  COUNT(*) AS lancamentos,
  ROUND(SUM(ABS(e.vlr)), 2) AS gasto
FROM `batalha-time-02-lxof.hackathon_dados.extrato_sintetico` AS e
JOIN grupos AS g ON g.macro = e.nom_cate_macro
WHERE e.id_usuario = @id_usuario
  AND e.tipo = 'S' AND g.grupo = 'discricionario'
  AND DATE(e.anomesdia) BETWEEN DATE_TRUNC(@data_corte, MONTH) AND @data_corte
GROUP BY macro, subcategoria
"""
NIVEL_CURTO = {consultas.NIVEL_1: ("Nível 1", "supérfluo"), consultas.NIVEL_2: ("Nível 2", "flexível"),
               consultas.NIVEL_3: ("Nível 3", "essencial")}
MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _sql() -> str:
    base = (usuario_real.visoes.PASTA_SQL / "_base_cliente.sql").read_text(encoding="utf-8")
    return t3.renderizar_sql(base + SQL_SUBCATEGORIAS)


def subcategorias_discricionarias(usuario: dict, corte: date) -> tuple[list[dict], dict]:
    executor = usuario_real._novo_executor()
    inicio = time.perf_counter()
    try:
        linhas = executor.executar(_sql(), {"id_usuario": usuario["id_usuario"], "data_corte": corte})
    except Exception as erro:
        raise usuario_real.FonteIndisponivel(f"subcategorias: {type(erro).__name__}: {erro}") from erro
    job = getattr(executor, "ultimo_job", {}) or {}
    selo = usuario_real._selo({"subcategorias": job.get("job_id")}, job.get("bytes_processados", 0),
                              (time.perf_counter() - inicio) * 1000)
    return linhas, selo


def gasto_ate_linha_de_corte(usuario: dict, corte: date) -> tuple[dict | None, dict | None]:
    """{(macro, subcategoria): gasto} do dia 1 do mês do corte até o corte. Falha -> (None, None): NAO_MEDIDO."""
    executor = usuario_real._novo_executor()
    inicio = time.perf_counter()
    try:
        linhas = executor.executar(t3.renderizar_sql(SQL_ATE_CORTE), {"id_usuario": usuario["id_usuario"], "data_corte": corte})
    except Exception:
        return None, None
    job = getattr(executor, "ultimo_job", {}) or {}
    selo = usuario_real._selo({"ate_linha_de_corte": job.get("job_id")}, job.get("bytes_processados", 0),
                              (time.perf_counter() - inicio) * 1000)
    return {(l["macro"], l["subcategoria"]): float(l["gasto"] or 0) for l in linhas}, selo


def _mes(anomes) -> str:
    anomes = int(anomes)
    return f"{MESES_PT[anomes % 100 - 1]}/{anomes // 100}"


def base_da_media(linhas: list[dict]) -> dict | None:
    """Meses completos antes do mês do corte que têm movimento: depende do usuário, não é fixo."""
    if not linhas or linhas[0].get("base_inicio") is None:
        return None
    l = linhas[0]
    ini, fim = int(l["base_inicio"]), int(l["base_fim"])
    return {"inicio": f"{ini // 100}-{ini % 100:02d}", "fim": f"{fim // 100}-{fim % 100:02d}",
            "meses": int(l["meses"]), "rotulo": f"{_mes(ini)} a {_mes(fim)}"}


def apresentar(p: dict, data_corte: str, base: dict | None, ate_corte: dict | None, selo: dict | None) -> dict:
    """Texto do painel (pedido do dono): chave, raciocínio e rodapé pela linha de corte. Parte pura."""
    corte_br = date.fromisoformat(data_corte).strftime("%d/%m/%Y")
    periodo = base["rotulo"] if base else "NAO_MEDIDO"
    for c in p["compromissos"]:
        nivel, nome = NIVEL_CURTO.get(c["nivel"], (c["nivel"], ""))
        acao = "pausa total" if c["meta"] == 0 else f"corte de {formatar_brl(c['corte'])}/mês"
        c["raciocinio"] = (f"Média de {formatar_brl(c['gasto_atual'])}/mês em {c['lancamentos_na_janela']} lançamentos "
                           f"({periodo}) · {nivel} ({nome}): {acao}.")
        c["ate_linha_de_corte"] = ("NAO_MEDIDO" if ate_corte is None
                                   else round(ate_corte.get((c["categoria_macro"], c["subcategoria"]), 0.0), 2))
    tot = p["totais"]
    raciocinio = [f"Renda média de {formatar_brl(tot['inflow_mensal'])}/mês e saldo médio de "
                  f"{formatar_brl(tot['surplus_mensal'])}/mês ({periodo})."]
    if tot["necessario_para_surplus_15"] > 0:
        raciocinio.append(f"Para guardar 15% da renda faltam {formatar_brl(tot['necessario_para_surplus_15'])}/mês: "
                          f"cortamos primeiro o supérfluo, depois o flexível, até {MAX_COMPROMISSOS} compromissos.")
        if tot["falta_apos_cortes"] > 0:
            raciocinio.append(f"Mesmo com os cortes faltam {formatar_brl(tot['falta_apos_cortes'])}/mês: o próximo passo "
                              "é renegociar dívidas, não cortar o essencial.")
    else:
        raciocinio.append(f"Você já guarda 15% da renda; nada a cortar. Reserva sugerida: {formatar_brl(tot['reserva'])}/mês.")
    base_txt = f"média de {periodo}, {base['meses']} meses completos" if base else "base NAO_MEDIDO"
    selo_txt = f" · fonte {selo['fonte']} · medido em {selo['medido_em']}" if selo else ""
    p["apresentacao"] = {
        "chave": "subcategoria",
        "linha_de_corte": data_corte,
        "base": {k: base[k] for k in ("inicio", "fim", "meses")} if base else "NAO_MEDIDO",
        "raciocinio": raciocinio,
        "rodape": (f"Com base nos seus registros até {corte_br} ({base_txt}). O mês da linha de corte não entra na "
                   f"média. Regra {REGRA}{selo_txt}"),
    }
    return p


def candidatas(linhas: list[dict]) -> list[dict]:
    """Margem de corte seguro por subcategoria, maior primeiro."""
    saida = []
    for linha in linhas:
        gasto = float(linha["gasto_mensal"] or 0)
        if gasto <= 0:
            continue
        nivel = consultas.classificar_essencialidade(linha["macro"])
        margem = round(gasto * PERCENTUAL_POR_NIVEL[nivel], 2)
        if margem > 0:
            saida.append({**linha, "gasto_mensal": gasto, "nivel": nivel, "margem": margem})
    return sorted(saida, key=lambda c: c["margem"], reverse=True)


def montar_proposta(resumo: dict, linhas: list[dict]) -> dict:
    """Parte pura da regra (testável sem BigQuery)."""
    inflow = float(resumo["inflow_mensal"] or 0)
    surplus = float(resumo["surplus_mensal"] or 0)
    necessario = round(max(0.0, t3.LIMIAR_SURPLUS * inflow - surplus), 2)
    compromissos, falta = [], necessario
    for c in candidatas(linhas):
        if falta <= 0 or len(compromissos) >= MAX_COMPROMISSOS:
            break
        corte = round(min(c["margem"], falta), 2)
        falta = round(falta - corte, 2)
        compromissos.append({
            "subcategoria": c["subcategoria"],
            "categoria_macro": c["macro"],
            "grupo": t3.MAPA_GRUPOS.get(c["macro"]),
            "nivel": c["nivel"],
            "gasto_atual": c["gasto_mensal"],
            "margem_corte_seguro": c["margem"],
            "corte": corte,
            "meta": round(c["gasto_mensal"] - corte, 2),
            "lancamentos_na_janela": c["lancamentos"],
            "texto": None,
        })
    for c in compromissos:
        if c["meta"] > 0:
            c["texto"] = f"Limitar {c['subcategoria']} a {formatar_brl(c['meta'])} em janeiro."
        else:  # Nível 1 cortado a 100 %: "limitar a R$ 0,00" lê-se mal
            c["texto"] = f"Pausar {c['subcategoria']} em janeiro (economia de {formatar_brl(c['corte'])})."
    reserva = round(max(0.0, min(surplus, PCT_RESERVA_50_30_20 * inflow)), 2) if necessario == 0 else 0.0
    liberado = round(sum(c["corte"] for c in compromissos), 2)
    if necessario == 0:
        estado = "LIVRE_SEM_CORTE"
    elif falta > 0:
        estado = "CORTE_INSUFICIENTE"
    else:
        estado = "OK"
    return {
        "regra": REGRA,
        "estado": estado,
        "compromissos": compromissos,
        "totais": {
            "inflow_mensal": inflow,
            "surplus_mensal": surplus,
            "necessario_para_surplus_15": necessario,
            "valor_liberado": liberado,
            "falta_apos_cortes": max(falta, 0.0),
            "reserva": reserva,
        },
    }


def formatar_brl(valor: float) -> str:
    inteiro, centavos = f"{abs(valor):,.2f}".split(".")
    texto = f"R$ {inteiro.replace(',', '.')},{centavos}"
    return f"−{texto}" if valor < 0 else texto


def proposta(referencia: str, data_corte=None) -> dict:
    perfil = usuario_real.perfil(referencia, data_corte=data_corte)
    corte = date.fromisoformat(perfil["data_corte"])
    linhas, selo_sub = subcategorias_discricionarias(perfil["usuario"], corte)
    ate_corte, selo_dez = gasto_ate_linha_de_corte(perfil["usuario"], corte)
    montada = apresentar(montar_proposta(perfil["resumo"], linhas), perfil["data_corte"],
                         base_da_media(linhas), ate_corte, selo_sub)
    return {
        "usuario": perfil["usuario"],
        "data_corte": perfil["data_corte"],
        "janela": perfil["janela"],
        "segmento_t3": perfil["resumo"]["segmento_t3"],
        **montada,
        "subcategorias_discricionarias": linhas,
        "selos": {"perfil": perfil["selo"], "subcategorias": selo_sub,
                  "ate_linha_de_corte": selo_dez or "NAO_MEDIDO"},
    }
