"""Guard: confere JSON e relê o extrato BigQuery antes de liberar texto."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from base import ConsultorBigQuery, Recusa, contrato, gravar_json, hash_json, validar_linha


def validar(evidencia: Path, proposta: Path, consultor=None) -> dict:
    inicio = time.perf_counter()
    registro = json.loads(evidencia.read_text(encoding="utf-8"))
    if registro.get("estado") != "AGUARDANDO_RESPOSTA":
        raise Recusa("evidência já encerrada ou inválida")
    regras = contrato()
    try:
        try:
            resposta = json.loads(proposta.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise Recusa("proposta não é JSON válido") from exc
        if type(resposta) is not dict or set(resposta) != set(regras["proposta_do_agente"]["campos_exatos"]):
            raise Recusa("estrutura JSON da proposta diverge do contrato")
        if any(type(resposta[chave]) is not str for chave in ("id_extracao", "id_usuario", "comportamento", "categoria", "campo")):
            raise Recusa("tipos da proposta divergem do contrato")
        if type(resposta["valor"]) not in (str, int, float):
            raise Recusa("tipo do valor diverge do contrato")
        if type(resposta["numero_usuario"]) is not int:
            raise Recusa("número do usuário não é inteiro")
        if resposta["id_extracao"] != registro["id_extracao"] or registro["fonte"] != regras["fonte"]:
            raise Recusa("identificador ou fonte divergem da evidência")
        selecao = registro["selecao"]
        validar_linha(selecao["linha"], regras)
        if selecao["campo"] != regras["extracao"]["campo_de_valor"]:
            raise Recusa("campo não contratado")
        consultor = consultor or ConsultorBigQuery(regras)
        usuarios = sorted(consultor.usuarios())
        numero = selecao["numero_usuario"]
        if (type(numero) is not int or numero < 1 or numero > len(usuarios)
                or len(usuarios) != registro["consultas"]["usuarios_candidatos"]
                or usuarios[numero - 1] != selecao["id_usuario"]):
            raise Recusa("número do sorteio divergiu da lista de UUIDs")
        movimentos = consultor.movimentos(selecao["id_usuario"])
        if sum(item == selecao["linha"] for item in movimentos) != selecao["ocorrencias_linha"]:
            raise Recusa("linha sorteada divergiu da base")
        if hash_json(selecao["linha"]) != registro["hash_linha_sha256"]:
            raise Recusa("hash da linha diverge")
        esperado = {
            "id_extracao": registro["id_extracao"], "numero_usuario": numero, "id_usuario": selecao["id_usuario"],
            "comportamento": regras["extracao"]["comportamento"][selecao["linha"]["tipo"]],
            "categoria": selecao["linha"]["nom_cate_macro"], "campo": selecao["campo"],
            "valor": selecao["linha"][selecao["campo"]],
        }
        if any(type(resposta[chave]) is not type(valor) or resposta[chave] != valor for chave, valor in esperado.items()):
            raise Recusa("proposta contém fato diferente do extrato")
        texto = regras["resposta_liberada"]["modelo_de_texto"].format(
            numero_usuario=numero, id_usuario=selecao["id_usuario"], comportamento=esperado["comportamento"],
            data_movimento=selecao["linha"]["anomesdia"], categoria=esperado["categoria"],
            valor=esperado["valor"],
        )
        liberada = {"aprovado": True, "id_extracao": registro["id_extracao"], "numero_usuario": numero, "id_usuario": selecao["id_usuario"], "resposta": texto}
        registro["estado"] = "APROVADO"
        registro["guard"] = {"decisao": "APROVADO", "verificado_em_utc": datetime.now(timezone.utc).isoformat(), "tempo_guard_ms": round((time.perf_counter() - inicio) * 1000, 3), "jobs": consultor.jobs, "hash_resposta_sha256": hash_json(liberada)}
        gravar_json(evidencia, registro)
        return liberada
    except Exception as exc:
        estado = "REPROVADO" if isinstance(exc, Recusa) else "NAO_MEDIDO"
        registro["estado"] = estado
        registro["guard"] = {"decisao": estado, "motivo": f"{type(exc).__name__}: {exc}", "verificado_em_utc": datetime.now(timezone.utc).isoformat(), "tempo_guard_ms": round((time.perf_counter() - inicio) * 1000, 3), "jobs": getattr(consultor, "jobs", [])}
        gravar_json(evidencia, registro)
        raise Recusa(str(exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidencia", type=Path, required=True)
    parser.add_argument("--proposta", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(validar(args.evidencia, args.proposta), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"RECUSADO: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
