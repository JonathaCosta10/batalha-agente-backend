"""Testa a especificacao colada pelo dono (N=316; dez: 48,4 % critico; T3 89,6/7,0/3,5) na base sintetica.

Uso, da raiz do projeto Django (ADC; chave de API e vedada):
    python docs/estudo-i-agora/medicoes/2026-09-27/q_spec_diagnostico_medir.py

1 dry-run + 1 consulta (q_spec_diagnostico_por_cliente.sql). Os agregados sao feitos aqui e gravados em
q_spec_diagnostico.json (sem id de cliente). Falhou a consulta: nada e gravado, imprime NAO_MEDIDO.

Regras da especificacao, como foram lidas aqui (declaradas no JSON em `regras_aplicadas`):
- margem = (Inflow - Outflow) / Inflow; critico = deficit (Surplus < 0) OU margem < 15 %.
- Vulneravel: Surplus < 0 OU margem < 15 % OU cheque especial OU juros.
- Esbanjador: 0,70 <= Outflow/Inflow <= 0,85, discricionario/Outflow >= mediana da base, sem cheque especial.
- Livre: margem >= 15 % em >= 3 meses (12 meses), sem credito emergencial, divida cara < 10 % do Inflow (12 meses).
- Precedencia: Vulneravel > Esbanjador > Livre; quem nao cai em nenhum fica `sem_segmento` (a spec nao o preve).
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median

from google.cloud import bigquery

AQUI = Path(__file__).resolve().parent
BRT = timezone(timedelta(hours=-3))
PROJETO = "batalha-time-02-lxof"
TABELA = "batalha-time-02-lxof.hackathon_dados.extrato_sintetico"
DATA_CORTE = "2025-12-22"
TETO_BYTES = 104_857_600
SQL = AQUI / "q_spec_diagnostico_por_cliente.sql"


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def margem(i, o):
    return (i - o) / i if i else None


def classificar(r, periodo, mediana_disc, cheque_def):
    i, o, d = r[f"{periodo}_inflow"], r[f"{periodo}_outflow"], r[f"{periodo}_disc"]
    m = margem(i, o)
    cheque = cheque_def(r)
    juros = r["n_juros"] > 0
    if m is None or (i - o) < 0 or m < 0.15 or cheque or juros:
        return "Vulneravel"
    ratio = o / i
    disc = (d / o) if o else 0
    if 0.70 <= ratio <= 0.85 and disc >= mediana_disc and not cheque:
        return "Esbanjador"
    emergencial = r["n_emprestimo"] > 0 or cheque
    divida_cara = (r["divida_cara_12m"] / r["inflow_12m"]) if r["inflow_12m"] else 1
    if r["meses_margem15_12m"] >= 3 and not emergencial and divida_cara < 0.10:
        return "Livre"
    return "sem_segmento"


def score_hipotetico(r, periodo):
    """Hipotese de score (a spec nao o define): 100 * margem / 0,15, recortado em [0, 100]."""
    m = margem(r[f"{periodo}_inflow"], r[f"{periodo}_outflow"])
    return 0.0 if m is None else max(0.0, min(100.0, 100.0 * m / 0.15))


def distribuicoes(linhas, rotulo, mediana_disc):
    n = len(linhas)
    out = {"n": n}
    for periodo in ("dez", "dez22", "janov"):
        deficit = [r for r in linhas if r[f"{periodo}_inflow"] - r[f"{periodo}_outflow"] < 0]
        m15 = [r for r in linhas if r not in deficit and (margem(r[f"{periodo}_inflow"], r[f"{periodo}_outflow"]) or 0) < 0.15]
        out[f"critico_{periodo}"] = {"deficit_n": len(deficit), "deficit_pct": pct(len(deficit), n),
                                     "margem_0_15_n": len(m15), "margem_0_15_pct": pct(len(m15), n),
                                     "critico_n": len(deficit) + len(m15), "critico_pct": pct(len(deficit) + len(m15), n)}
    cheques = {
        "saldo_apos_negativo": lambda r: r["n_saldo_negativo"] > 0,
        "micro_Cheque": lambda r: r["n_cheque"] > 0,
        "sem_proxy": lambda r: False,
    }
    for periodo in ("dez", "janov"):
        for nome_cheque, fn in cheques.items():
            seg = {}
            for r in linhas:
                s = classificar(r, periodo, mediana_disc, fn)
                seg.setdefault(s, []).append(score_hipotetico(r, periodo))
            out[f"t3_{periodo}_cheque={nome_cheque}"] = {
                s: {"n": len(v), "pct": pct(len(v), n), "score_hipotetico_medio": round(mean(v), 1)}
                for s, v in sorted(seg.items())}
    # quais condicoes empurram para Vulneravel (sem precedencia, cada uma sozinha)
    out["gatilhos_vulneravel_janov"] = {
        "deficit": sum(1 for r in linhas if r["janov_inflow"] < r["janov_outflow"]),
        "margem_lt_15": sum(1 for r in linhas if (margem(r["janov_inflow"], r["janov_outflow"]) or 0) < 0.15),
        "juros_pagos_12m": sum(1 for r in linhas if r["n_juros"] > 0),
        "saldo_apos_negativo_12m": sum(1 for r in linhas if r["n_saldo_negativo"] > 0),
        "micro_Cheque_12m": sum(1 for r in linhas if r["n_cheque"] > 0),
    }
    return out


def main() -> int:
    agora = datetime.now(BRT)
    cliente = bigquery.Client(project=PROJETO)
    sql = SQL.read_text(encoding="utf-8")
    params = [bigquery.ScalarQueryParameter("data_corte", "DATE", DATA_CORTE)]
    try:
        dry = cliente.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params, dry_run=True,
                                                                     use_query_cache=False))
        bytes_dry = dry.total_bytes_processed
        print(f"dry-run: {bytes_dry} bytes")
        if bytes_dry > TETO_BYTES:
            print(f"NAO_MEDIDO (dry-run {bytes_dry} > teto {TETO_BYTES})", file=sys.stderr)
            return 1
        job = cliente.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
        linhas = [dict(x) for x in job.result()]
    except Exception as erro:
        print(f"NAO_MEDIDO ({type(erro).__name__}: {erro})", file=sys.stderr)
        return 1

    for r in linhas:
        r["dez_inflow"], r["dez_outflow"] = r["dez_inflow"] or 0.0, r["dez_outflow"] or 0.0
        r["dez_disc"] = r["dez_discricionario"] or 0.0
        r["dez22_disc"] = r["dez_disc"]
        r["janov_inflow"], r["janov_outflow"] = r["inflow_medio_janov"], r["outflow_medio_janov"]
        r["janov_disc"] = r["discricionario_medio_janov"]
    n = len(linhas)
    med_disc = median((r["janov_disc"] / r["janov_outflow"]) for r in linhas if r["janov_outflow"])

    # --- Hipoteses para N=316: contagem de cada filtro candidato ---
    filtros = {
        "transacao_em_dezembro": lambda r: r["transacoes_dez"] > 0,
        "deficit_dezembro_mes_inteiro": lambda r: r["dez_inflow"] - r["dez_outflow"] < 0,
        "deficit_dezembro_ate_22": lambda r: r["dez22_inflow"] - r["dez22_outflow"] < 0,
        "deficit_media_janov": lambda r: r["janov_inflow"] < r["janov_outflow"],
        "deficit_12m_acumulado": lambda r: r["inflow_12m"] < r["outflow_12m"],
        "saldo_apos_negativo_12m (proxy cheque especial)": lambda r: r["n_saldo_negativo"] > 0,
        "saldo_apos_negativo_dez": lambda r: r["n_saldo_negativo_dez"] > 0,
        "micro_Cheque_12m": lambda r: r["n_cheque"] > 0,
        "juros_pagos_12m": lambda r: r["n_juros"] > 0,
        "juros_pagos_dez": lambda r: r["n_juros_dez"] > 0,
        "tarifa_ou_multa_12m": lambda r: r["n_tarifa_multa"] > 0,
        "emprestimo_12m": lambda r: r["n_emprestimo"] > 0,
        "financiamento_imovel_12m": lambda r: r["n_financiamento_imovel"] > 0,
        "sem_salario_clt": lambda r: r["n_clt"] == 0,
        "beneficio_inss": lambda r: r["n_inss"] > 0,
        "paga_aluguel": lambda r: r["n_aluguel_pago"] > 0,
        "recebe_aluguel": lambda r: r["n_aluguel_recebido"] > 0,
        "bonus_plr": lambda r: r["n_plr"] > 0,
        "algum_parcelado": lambda r: r["n_parcelado"] > 0,
        "renda_media_janov_lt_5000": lambda r: r["janov_inflow"] < 5000,
        "renda_media_janov_lt_6000": lambda r: r["janov_inflow"] < 6000,
        "renda_media_janov_lt_7000": lambda r: r["janov_inflow"] < 7000,
        "renda_media_janov_lt_8000": lambda r: r["janov_inflow"] < 8000,
    }
    for k in range(1, 13):
        filtros[f"meses_deficit_12m_ge_{k}"] = (lambda kk: lambda r: r["meses_deficit_12m"] >= kk)(k)
    hipoteses = {nome: sum(1 for r in linhas if f(r)) for nome, f in filtros.items()}
    bate_316 = [nome for nome, c in hipoteses.items() if c == 316]
    rendas = sorted(r["janov_inflow"] for r in linhas)
    renda_corte = {"renda_316a_menor": round(rendas[315], 2), "renda_317a_menor": round(rendas[316], 2),
                   "renda_316a_maior": round(rendas[-316], 2), "renda_317a_maior": round(rendas[-317], 2)}

    base = distribuicoes(linhas, "base", med_disc)
    recortes = {nome: distribuicoes([r for r in linhas if filtros[nome](r)], nome, med_disc) for nome in bate_316}

    # --- Reconstrucao: onde aparecem 28,8 % / 19,6 % (91 / 62 de 316; 288 / 196 de 1000)? ---
    coorte = [r for r in linhas if filtros["deficit_dezembro_mes_inteiro"](r)]

    def contar(grupo, pares):
        d = sum(1 for i, o in pares if i - o < 0)
        m = sum(1 for i, o in pares if i - o >= 0 and (i == 0 or (i - o) / i < 0.15))
        return {"deficit_n": d, "deficit_pct": pct(d, grupo), "margem_0_15_n": m, "margem_0_15_pct": pct(m, grupo)}

    varredura = {"por_mes": {}, "dezembro_por_dia_de_corte": {}}
    for nome, grupo in (("base_1000", linhas), ("coorte_316", coorte)):
        for am in sorted({x["anomes"] for r in linhas for x in r["meses_serie"]}):
            pares = [next(((x["inflow"], x["outflow"]) for x in r["meses_serie"] if x["anomes"] == am), (0.0, 0.0))
                     for r in grupo]
            varredura["por_mes"][f"{nome}|{am}"] = contar(len(grupo), pares)
        for dia in range(1, 32):
            pares = [(sum(x["e"] for x in (r["dez_dias"] or []) if x["dia"] <= dia),
                      sum(x["s"] for x in (r["dez_dias"] or []) if x["dia"] <= dia)) for r in grupo]
            varredura["dezembro_por_dia_de_corte"][f"{nome}|ate_{dia:02d}"] = contar(len(grupo), pares)
    alvo = {("coorte_316", 91), ("coorte_316", 62), ("base_1000", 288), ("base_1000", 196)}
    casamentos = [f"{k}: {campo}={v[campo]}" for secao in varredura.values() for k, v in secao.items()
                  for campo in ("deficit_n", "margem_0_15_n") if (k.split("|")[0], v[campo]) in alvo]

    # --- Reconstrucao da T3 da spec no recorte 316, media jan-nov, SEM gatilho de juros/cheque ---
    def t3_simples(r):
        i, o = r["janov_inflow"], r["janov_outflow"]
        m = margem(i, o)
        if m is None or m < 0.15:
            return "Vulneravel"
        return "Esbanjador" if o / i >= 0.70 else "Livre"

    def scores(r):
        m = margem(r["janov_inflow"], r["janov_outflow"]) or 0.0
        ratio = r["janov_outflow"] / r["janov_inflow"]
        return {"clip_100_margem_sobre_15": max(0.0, min(100.0, 100.0 * m / 0.15)),
                "clip_100_mais_100_margem": max(0.0, min(100.0, 100.0 * (1 + m))),
                "clip_100_inflow_sobre_outflow": max(0.0, min(100.0, 100.0 / ratio)),
                "clip_50_mais_margem_sobre_30": max(0.0, min(100.0, 50.0 + 100.0 * m / 0.30))}

    reconstrucao = {}
    for nome, grupo in (("coorte_316", coorte), ("base_1000", linhas)):
        seg = {}
        for r in grupo:
            seg.setdefault(t3_simples(r), []).append(scores(r))
        reconstrucao[nome] = {s: {"n": len(v), "pct": pct(len(v), len(grupo)),
                                  **{f"score_medio_{k}": round(mean(x[k] for x in v), 1) for k in v[0]}}
                              for s, v in sorted(seg.items())}

    rel = {
        "consulta": SQL.name,
        "fonte": TABELA,
        "medido_em": agora.strftime("%Y-%m-%dT%H:%M BRT"),
        "autenticacao": "ADC",
        "data_corte": DATA_CORTE,
        "job_id": job.job_id,
        "bytes_dry_run": bytes_dry,
        "bytes_processados": job.total_bytes_processed,
        "clientes": n,
        "regras_aplicadas": {
            "inflow_outflow": "tipo='E' / tipo='S', soma ABS(vlr); a base nao tem coluna V/True",
            "critico": "deficit (Surplus<0) + margem em [0, 15%) ; disjuntos",
            "precedencia": "Vulneravel > Esbanjador > Livre > sem_segmento",
            "vulneravel": "Surplus<0 OU margem<15% OU cheque especial (proxy) OU Juros pagos em 12m",
            "esbanjador": "0,70<=Outflow/Inflow<=0,85 E discricionario/Outflow >= mediana da base "
                          f"({round(med_disc, 4)}) E sem cheque especial",
            "livre": "margem>=15% em >=3 dos 12 meses E sem emprestimo/cheque E divida cara 12m < 10% do inflow 12m",
            "divida_cara": "Juros pagos + Outras tarifas financeiras + Anuidade e pacote de servico + Multa por atraso",
            "cheque_especial": "SEM categoria na base; proxies: saldo_apos<0 em algum lancamento, ou micro 'Cheque'",
            "periodos": "dez = anomes 202512 inteiro; dez22 = ate 2025-12-22; janov = media mensal jan-nov/2025",
            "score": "a spec nao define; score_hipotetico = clip(100*margem/0,15, 0, 100) do periodo",
        },
        "categorias_da_base": {
            "cheque_especial": "NAO_EXISTE como categoria (proxy saldo_apos<0; micro 'Cheque' e pagamento em cheque)",
            "juros_e_tarifas": ["Produtos financeiros/Juros pagos", "Produtos financeiros/Outras tarifas financeiras",
                                "Produtos financeiros/Anuidade e pacote de servico", "Outros gastos/Multa por atraso"],
            "financiamento": ["Emprestimos e financiamentos/Financiamento de imovel",
                              "Emprestimos e financiamentos/Emprestimos",
                              "Emprestimos e financiamentos/Outros emprestimos", "Produtos financeiros/Consorcio"],
            "fonte_categorias": "q02_categorias.json (2026-09-27T03:48 BRT)",
        },
        "hipoteses_n316": hipoteses,
        "hipoteses_que_dao_316": bate_316,
        "renda_em_torno_do_corte_316": renda_corte,
        "distribuicao_base_1000": base,
        "distribuicao_recortes_316": recortes,
        "reconstrucao_t3_spec": {
            "regra": "media jan-nov; Vulneravel = margem<15% (inclui deficit); Esbanjador = Outflow/Inflow>=0,70; "
                     "Livre = resto (margem>30%); SEM juros/cheque/discricionario",
            "resultado": reconstrucao,
        },
        "varredura_28_8_e_19_6": {"casamentos_exatos": casamentos, **varredura},
    }
    destino = AQUI / "q_spec_diagnostico.json"
    destino.write_text(json.dumps(rel, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: rel[k] for k in ("medido_em", "job_id", "bytes_processados", "hipoteses_n316",
                                          "hipoteses_que_dao_316", "renda_em_torno_do_corte_316")},
                     ensure_ascii=False, indent=1))
    print(json.dumps(reconstrucao, ensure_ascii=False, indent=1))
    print("casamentos:", casamentos)
    for k, v in varredura["por_mes"].items():
        print(k, v)
    for k in ("coorte_316|ate_22", "coorte_316|ate_31", "base_1000|ate_22"):
        print(k, varredura["dezembro_por_dia_de_corte"][k])
    return 0


if __name__ == "__main__":
    sys.exit(main())
