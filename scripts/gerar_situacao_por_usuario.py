"""
Pré-calcula a SITUAÇÃO financeira de cada um dos 1.000 id_usuario do CSV da verdade, para o sorteio de
perfil-usuario/definir/ {"usuario":"aleatorio"} e do "Testar próximo perfil" variarem por situação.

Mesma fonte e mesma regra da abertura do i-agora (README do front, seção 12):
- fonte: o extrato no BigQuery (apps/i_agora/fonte.py, TABELA), pelo mesmo executor (ADC, dry-run, teto de bytes);
- janela: o último mês encerrado com dados de cada cliente (período < mês corrente UTC), tipo E = entradas,
  tipo S = saídas, valores em ABS — o mesmo WITH movements de fonte.SQL_SNAPSHOT, agrupado por id_usuario numa
  consulta só em vez de 1.000;
- regra: apps.i_agora.domain.situacao_do_mes (a função que a abertura chama), importada, não copiada.

Id do CSV sem linhas na fonte, com movimento sem direção/valor válido (o mesmo teste de load_ref) ou com período
não reconciliado fica NAO_MEDIDO, com o motivo. Nada é adivinhado.

Saída: data/situacao_por_usuario.json  {selo: {fonte, regra, gerado_em, cutoff, job, total, contagem}, situacao: {id: cat}}
Só a categoria sai por id (sem valores): o ficheiro vai para o repositório.

Uso (na pasta backend):  .venv\\Scripts\\python.exe scripts\\gerar_situacao_por_usuario.py
"""

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")

import django  # noqa: E402

django.setup()

from apps.context_agent_datadriven.services import perfil_usuario, usuario_real  # noqa: E402
from apps.i_agora import domain, fonte  # noqa: E402
from apps.i_agora.sessao import ARQUIVO_SITUACAO, NAO_MEDIDO  # noqa: E402

SQL_LOTE = f"""
WITH movements AS (
  SELECT CAST(id_usuario AS STRING) AS id_usuario, {fonte._PERIODO} AS period, SAFE_CAST(vlr AS NUMERIC) AS amount,
         LOWER(CAST(tipo AS STRING)) = 'e' AS is_in, LOWER(CAST(tipo AS STRING)) = 's' AS is_out
  FROM `{fonte.TABELA}`
  WHERE {fonte._PERIODO} < @cutoff),
last_period AS (SELECT id_usuario, MAX(period) AS period FROM movements GROUP BY id_usuario)
SELECT m.id_usuario, m.period,
       CAST(SUM(IF(is_in, ABS(amount), 0)) AS STRING) AS inflows,
       CAST(SUM(IF(is_out, ABS(amount), 0)) AS STRING) AS outflows,
       COUNTIF(amount IS NULL OR NOT (COALESCE(is_in, FALSE) OR COALESCE(is_out, FALSE))) AS invalid
FROM movements m JOIN last_period USING (id_usuario, period)
GROUP BY m.id_usuario, m.period
"""

CENTAVO = Decimal(".01")


def classificar(ids, linhas):
    """-> ({id: categoria}, {id: motivo NAO_MEDIDO}). Mesmos testes de fonte.load_ref, mesma regra do domain."""
    por_id = {}
    for linha in linhas:
        por_id.setdefault(str(linha["id_usuario"]), []).append(linha)
    situacao, motivos = {}, {}
    for ref in ids:
        rows = por_id.get(ref)
        if not rows:
            motivo = "sem movimentos em mes encerrado na fonte"
        elif any(int(r["invalid"]) for r in rows):
            motivo = "movimentos sem direcao/valor validos"
        elif len({r["period"] for r in rows}) != 1:
            motivo = "periodos nao reconciliados"
        else:
            entradas = sum((Decimal(r["inflows"]) for r in rows), Decimal(0)).quantize(CENTAVO)
            saidas = sum((Decimal(r["outflows"]) for r in rows), Decimal(0)).quantize(CENTAVO)
            situacao[ref] = domain.situacao_do_mes(entradas, saidas)
            continue
        situacao[ref], motivos[ref] = NAO_MEDIDO, motivo
    return situacao, motivos


def main() -> int:
    ids = sorted(perfil_usuario._carregar()["por_uuid"])
    cutoff = datetime.now(timezone.utc).strftime("%Y-%m")
    executor = usuario_real._novo_executor()
    try:
        linhas = executor.executar(SQL_LOTE, {"cutoff": cutoff})
    except Exception as erro:  # noqa: BLE001 - o instrumento diz que não mediu, e porquê
        print(json.dumps({"estado": "NAO_MEDIDO", "erro": f"{type(erro).__name__}: {erro}"}, ensure_ascii=False))
        return 1
    situacao, motivos = classificar(ids, linhas)
    contagem = dict(sorted(Counter(situacao.values()).items()))
    job = getattr(executor, "ultimo_job", {}) or {}
    selo = {
        "fonte": fonte.TABELA,
        "natureza_da_base": "sintetica",
        "catalogo": "data/usuarios_verdade.csv",
        "regra": domain.REGRA_SITUACAO,
        "versao": 1,
        "gerado_em": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "cutoff": cutoff,
        "job_id": job.get("job_id"),
        "bytes_processados": job.get("bytes_processados"),
        "total": len(situacao),
        "contagem": contagem,
        "gerado_por": "scripts/gerar_situacao_por_usuario.py",
    }
    saida = {"selo": selo, "situacao": situacao, "nao_medido_motivo": motivos}
    ARQUIVO_SITUACAO.write_text(json.dumps(saida, ensure_ascii=False, indent=1, sort_keys=False) + "\n",
                                encoding="utf-8")
    print(json.dumps(selo, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
