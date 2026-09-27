"""
Análise estatística aplicada à segmentação T3 (entrada: linhas de sql/populacao_t3.sql).

    classificar_populacao    segmento por cliente com t3.classificar_t3
    descritiva               n, média, desvio, p10..p90
    ic_bootstrap_proporcoes  IC 95% da participação de cada segmento (reamostragem de clientes)
    ic_bootstrap_mediana     IC 95% da mediana de uma métrica
    sensibilidade_do_limiar  participação e migração entre segmentos com limiar 10% / 15% / 20%
    spearman_permutacao      correlação de postos e p-valor por permutação

Só agregados saem daqui: nenhum id de cliente vai para a medição.
Sementes fixas: a mesma entrada dá o mesmo número.
"""

import numpy as np
import pandas as pd

from . import t3

PERCENTIS = (10, 25, 50, 75, 90)


def classificar_populacao(linhas: list[dict], limiar: float = t3.LIMIAR_SURPLUS) -> pd.DataFrame:
    df = pd.DataFrame(linhas)
    for col in ("inflow", "outflow", "essencial", "compromisso", "discricionario", "nao_classificado"):
        df[col] = df[col].astype(float)
    df["surplus"] = df["inflow"] - df["outflow"]
    renda = df["inflow"].where(df["inflow"] > 0)
    df["taxa_surplus"] = df["surplus"] / renda
    df["pct_discricionario"] = df["discricionario"] / renda
    df["pct_compromisso"] = df["compromisso"] / renda
    df["pct_essencial"] = df["essencial"] / renda
    df["segmento_t3"] = [t3.classificar_t3(i, o, d, limiar)
                         for i, o, d in zip(df["inflow"], df["outflow"], df["discricionario"])]
    return df


def descritiva(valores) -> dict:
    v = pd.Series(valores, dtype=float).dropna()
    if v.empty:
        return {"n": 0}
    saida = {"n": int(v.size), "media": float(v.mean()), "desvio": float(v.std(ddof=1)) if v.size > 1 else None}
    saida.update({f"p{p}": float(np.percentile(v, p)) for p in PERCENTIS})
    return saida


def ic_bootstrap_proporcoes(segmentos, reamostras: int = 2000, semente: int = 20251222) -> dict:
    s = np.asarray(list(segmentos))
    rng = np.random.default_rng(semente)
    amostras = rng.integers(0, s.size, size=(reamostras, s.size))
    saida = {}
    for seg in t3.SEGMENTOS:
        indicador = (s == seg)
        props = indicador[amostras].mean(axis=1)
        saida[seg] = {"n": int(indicador.sum()), "pct": float(indicador.mean() * 100),
                      "ic95": [float(np.percentile(props, 2.5) * 100), float(np.percentile(props, 97.5) * 100)]}
    return saida


def ic_bootstrap_mediana(valores, reamostras: int = 2000, semente: int = 20251222) -> dict:
    v = pd.Series(valores, dtype=float).dropna().to_numpy()
    if v.size < 3:
        return {"n": int(v.size), "mediana": None, "ic95": None, "nota": "NAO_MEDIDO: n<3"}
    rng = np.random.default_rng(semente)
    medianas = np.median(v[rng.integers(0, v.size, size=(reamostras, v.size))], axis=1)
    return {"n": int(v.size), "mediana": float(np.median(v)),
            "ic95": [float(np.percentile(medianas, 2.5)), float(np.percentile(medianas, 97.5))]}


def sensibilidade_do_limiar(linhas: list[dict], limiares=(0.10, 0.15, 0.20)) -> dict:
    base = classificar_populacao(linhas)["segmento_t3"]
    saida = {}
    for limiar in limiares:
        seg = classificar_populacao(linhas, limiar)["segmento_t3"]
        migracao = pd.crosstab(base, seg).reindex(index=t3.SEGMENTOS, columns=t3.SEGMENTOS, fill_value=0)
        saida[f"{limiar:.2f}"] = {
            "pct": {s: float((seg == s).mean() * 100) for s in t3.SEGMENTOS},
            "mudaram_vs_015": int((seg != base).sum()),
            "migracao_de_015_para_este": {a: {b: int(migracao.loc[a, b]) for b in t3.SEGMENTOS} for a in t3.SEGMENTOS},
        }
    return saida


def spearman_permutacao(x, y, permutacoes: int = 5000, semente: int = 20251222) -> dict:
    par = pd.DataFrame({"x": x, "y": y}, dtype=float).dropna()
    if len(par) < 3:
        return {"n": len(par), "rho": None, "p_valor": None, "nota": "NAO_MEDIDO: n<3"}
    rx, ry = par["x"].rank().to_numpy(), par["y"].rank().to_numpy()
    rho = float(np.corrcoef(rx, ry)[0, 1])
    rng = np.random.default_rng(semente)
    nulos = np.array([np.corrcoef(rx, rng.permutation(ry))[0, 1] for _ in range(permutacoes)])
    p = float((np.sum(np.abs(nulos) >= abs(rho)) + 1) / (permutacoes + 1))
    return {"n": int(len(par)), "rho": rho, "p_valor": p, "permutacoes": permutacoes}


def relatorio(linhas: list[dict]) -> dict:
    """Tudo o que vai para medicoes/<data>/estatistica_t3.json."""
    df = classificar_populacao(linhas)
    metricas = ("inflow", "outflow", "surplus", "taxa_surplus", "pct_essencial", "pct_compromisso",
                "pct_discricionario", "cv_inflow")
    por_segmento = {}
    for seg in t3.SEGMENTOS:
        sub = df[df["segmento_t3"] == seg]
        por_segmento[seg] = {
            "descritiva": {m: descritiva(sub[m]) for m in metricas},
            "mediana_taxa_surplus": ic_bootstrap_mediana(sub["taxa_surplus"]),
            "mediana_inflow": ic_bootstrap_mediana(sub["inflow"]),
        }
    return {
        "clientes": int(len(df)),
        "clientes_sem_inflow": int((df["inflow"] <= 0).sum()),
        "saidas_sem_grupo": int(df["saidas_sem_grupo"].sum()),
        "meses_por_cliente": descritiva(df["meses"]),
        "participacao": ic_bootstrap_proporcoes(df["segmento_t3"]),
        "por_segmento": por_segmento,
        "sensibilidade_do_limiar": sensibilidade_do_limiar(linhas),
        "correlacoes": {
            "pct_discricionario_vs_taxa_surplus": spearman_permutacao(df["pct_discricionario"], df["taxa_surplus"]),
            "pct_compromisso_vs_taxa_surplus": spearman_permutacao(df["pct_compromisso"], df["taxa_surplus"]),
            "cv_inflow_vs_taxa_surplus": spearman_permutacao(df["cv_inflow"], df["taxa_surplus"]),
        },
    }
