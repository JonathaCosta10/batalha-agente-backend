"""Sorteia UUID e informação do extrato BigQuery e registra evidência inicial."""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from base import ConsultorBigQuery, Recusa, contrato, gravar_json, hash_json, validar_uuid


def preparar(evidencia: Path, consultor=None) -> dict:
    inicio = time.perf_counter()
    if evidencia.exists():
        raise Recusa("evidência já existe; use caminho único por clique")
    regras = contrato()
    consultor = consultor or ConsultorBigQuery(regras)
    usuarios = sorted(consultor.usuarios())
    if not usuarios:
        raise Recusa("nenhum usuário encontrado até a data de corte")
    numero_usuario = secrets.randbelow(len(usuarios)) + 1
    id_usuario = usuarios[numero_usuario - 1]
    validar_uuid(id_usuario)
    movimentos = consultor.movimentos(id_usuario)
    if not movimentos:
        raise Recusa("usuário sorteado sem movimentos no corte")
    linha = secrets.choice(movimentos)
    campo = regras["extracao"]["campo_de_valor"]
    identificador = str(uuid.uuid4())
    selecao = {
        "numero_usuario": numero_usuario,
        "id_usuario": id_usuario,
        "linha": linha,
        "campo": campo,
        "valor": linha[campo],
        "comportamento": regras["extracao"]["comportamento"][linha["tipo"]],
        "categoria": linha["nom_cate_macro"],
        "ocorrencias_linha": sum(item == linha for item in movimentos),
    }
    proposta = {chave: selecao[chave] for chave in ("numero_usuario", "id_usuario", "comportamento", "categoria", "campo", "valor")}
    proposta["id_extracao"] = identificador
    registro = {
        "versao": regras["versao"], "id_extracao": identificador,
        "criado_em_utc": datetime.now(timezone.utc).isoformat(),
        "fonte": regras["fonte"], "selecao": selecao,
        "hash_linha_sha256": hash_json(linha),
        "consultas": {"jobs": consultor.jobs, "usuarios_candidatos": len(usuarios), "movimentos_do_usuario": len(movimentos)},
        "tempo_preparo_ms": round((time.perf_counter() - inicio) * 1000, 3),
        "estado": "AGUARDANDO_RESPOSTA", "guard": None,
    }
    gravar_json(evidencia, registro)
    return {"proposta_esperada": proposta, "id_evidencia": identificador}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidencia", type=Path, required=True)
    args = parser.parse_args()
    inicio = time.perf_counter()
    regras = None
    consultor = None
    try:
        regras = contrato()
        consultor = ConsultorBigQuery(regras)
        print(json.dumps(preparar(args.evidencia, consultor), ensure_ascii=False, allow_nan=False))
        return 0
    except Exception as exc:
        if not args.evidencia.exists():
            falha = {
                "versao": regras["versao"] if regras else "NAO_MEDIDO",
                "id_extracao": str(uuid.uuid4()),
                "criado_em_utc": datetime.now(timezone.utc).isoformat(),
                "fonte": regras["fonte"] if regras else None,
                "selecao": None, "hash_linha_sha256": None,
                "consultas": {"jobs": getattr(consultor, "jobs", [])},
                "tempo_preparo_ms": round((time.perf_counter() - inicio) * 1000, 3),
                "estado": "NAO_MEDIDO", "guard": None,
                "falha": f"{type(exc).__name__}: {exc}",
            }
            try:
                gravar_json(args.evidencia, falha)
            except OSError:
                pass
        print(f"NAO_MEDIDO: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
