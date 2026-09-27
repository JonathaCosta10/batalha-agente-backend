"""Mede a segmentação T3 no BigQuery real e prova o guard ponta a ponta.

Autenticação: ADC (ver medir.py). Uso, da raiz do projeto Django:

    python docs/estudo-i-agora/sql/medir_t3.py

Grava em docs/estudo-i-agora/medicoes/<AAAA-MM-DD>/:
    estatistica_t3.json  agregados de estatistica.relatorio (sem id de cliente)
    guard_e2e.json       por segmento, 1 cliente real: envio correto, envio adulterado
                         e envio com tom fora da faixa, cada um com o veredito do guard;
                         e a concordância segmento SQL x t3.classificar_t3
Se a consulta falhar, nada é gravado: sem medição não há número.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora import estatistica, guard, t3, visoes  # noqa: E402

BRT = timezone(timedelta(hours=-3))
TABELA = "batalha-time-02-lxof.hackathon_dados.extrato_sintetico"


def brl(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def pct(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",") + "%"


def envio_correto(segmento: str, cliente: str, executor) -> dict:
    """Texto montado só com números da visão, no tom do segmento."""
    if segmento == t3.VULNERAVEL:
        v = visoes.consultar_visao("dividas", cliente, executor=executor)["linha"]
        texto = (f"Sei que o mês está em aperto. Vamos organizar juntos, passo a passo: o compromisso "
                 f"financeiro soma {brl(v['compromisso_mensal'])} por mês, {pct(v['pct_inflow_comprometido'])} "
                 f"do que entra. O primeiro passo é renegociar esse valor com segurança.")
        dados = {"compromisso_mensal": v["compromisso_mensal"], "pct_inflow_comprometido": v["pct_inflow_comprometido"]}
        return {"topico": "dividas", "dados": dados, "texto": texto}
    if segmento == t3.ESBANJADOR:
        v = visoes.consultar_visao("discricionario", cliente, executor=executor)["linha"]
        texto = (f"Há folga possível: o discricionário soma {brl(v['discricionario_mensal'])} por mês, e "
                 f"{v['maior_categoria_discricionaria']} é a maior parte. Uma meta de reduzir esse grupo "
                 f"alivia o aperto e diminui o risco.")
        dados = {"discricionario_mensal": v["discricionario_mensal"],
                 "maior_categoria_discricionaria": v["maior_categoria_discricionaria"]}
        return {"topico": "discricionario", "dados": dados, "texto": texto}
    v = visoes.consultar_visao("perfil_t3", cliente, executor=executor)["linha"]
    texto = (f"Sua sobra média é de {brl(v['surplus_mensal'])} por mês ({pct(v['taxa_surplus_pct'])} da renda). "
             f"É uma boa base para planejar uma reserva, sem promessa de retorno; o risco de cada aplicação "
             f"precisa ser avaliado.")
    dados = {"surplus_mensal": v["surplus_mensal"], "taxa_surplus_pct": v["taxa_surplus_pct"]}
    return {"topico": "perfil_t3", "dados": dados, "texto": texto}


def main() -> int:
    agora = datetime.now(BRT)
    selo = {"fonte": TABELA, "medido_em": agora.strftime("%Y-%m-%dT%H:%M BRT"), "autenticacao": "ADC",
            "data_corte": visoes.DATA_CORTE_TESE.isoformat(), "limiar_surplus": t3.LIMIAR_SURPLUS}
    executor = visoes.ExecutorBigQuery()
    try:
        sql = t3.renderizar_sql((visoes.PASTA_SQL / "populacao_t3.sql").read_text(encoding="utf-8"))
        populacao = executor.executar(sql, {"data_corte": visoes.DATA_CORTE_TESE})
        job_populacao = dict(executor.ultimo_job)
    except Exception as erro:
        print(f"populacao_t3.sql: NAO_MEDIDO ({type(erro).__name__}: {erro})", file=sys.stderr)
        return 1

    saida = RAIZ / "docs" / "estudo-i-agora" / "medicoes" / agora.strftime("%Y-%m-%d")
    saida.mkdir(parents=True, exist_ok=True)
    rel = {"consulta": "populacao_t3.sql", **selo, **job_populacao, **estatistica.relatorio(populacao)}
    (saida / "estatistica_t3.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"estatistica_t3.json: {rel['clientes']} clientes, participação "
          + ", ".join(f"{s} {p['pct']:.1f}%" for s, p in rel["participacao"].items()))

    df = estatistica.classificar_populacao(populacao)
    casos = []
    for seg in t3.SEGMENTOS:
        sub = df[df["segmento_t3"] == seg]
        if sub.empty:
            casos.append({"segmento": seg, "resultado": "NAO_MEDIDO: segmento vazio"})
            continue
        cliente = sub.iloc[(sub["taxa_surplus"] - sub["taxa_surplus"].median()).abs().argsort().iloc[0]]["id_usuario"]
        perfil = visoes.consultar_visao("perfil_t3", cliente, executor=executor)["linha"]
        base = {"id_usuario": cliente, "data_corte": visoes.DATA_CORTE_TESE.isoformat(), "segmento_t3": seg,
                **envio_correto(seg, cliente, executor)}
        campo = next(k for k, v in base["dados"].items() if isinstance(v, float))
        adulterado = {**base, "dados": {**base["dados"], campo: round(base["dados"][campo] + 100, 2)}}
        fora_do_tom = {**base, "texto": base["texto"] + " Aproveite, é incrível e fantástico, sem risco!!"}
        casos.append({
            "segmento": seg,
            "id_usuario": cliente,
            "segmento_sql": perfil["segmento_t3"],
            "segmento_python": t3.classificar_t3(perfil["inflow_mensal"], perfil["outflow_mensal"],
                                                 perfil["discricionario_mensal"]),
            "envios": {nome: {"envio": e, "retorno": guard.verificar_envio(e, executor)}
                       for nome, e in (("correto", base), ("adulterado", adulterado), ("fora_do_tom", fora_do_tom))},
        })
    (saida / "guard_e2e.json").write_text(json.dumps({**selo, "casos": casos}, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    for c in casos:
        if "envios" in c:
            print(f"guard {c['segmento']}: SQL={c['segmento_sql']} py={c['segmento_python']} | "
                  + " ".join(f"{n}={r['retorno']['veredito']}" for n, r in c["envios"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
