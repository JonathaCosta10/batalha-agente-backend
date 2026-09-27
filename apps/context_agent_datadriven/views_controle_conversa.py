"""
Controle da conversa: o roteiro de falas do front (conversa/roteiro.json) servido pelo backend.

GET controle-conversa/                 -> roteiro inteiro
GET controle-conversa/?estagio=invite  -> só as falas desse estágio
Documentação: docs/controle-da-conversa.md.
"""

import json
from pathlib import Path

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

ARQUIVO_ROTEIRO = Path(__file__).resolve().parent / "conversa" / "roteiro.json"
DESTINOS_EXTREMO = {"humano", "seguranca"}
MOTIVOS_EXTREMO = {"flerte", "ameaca", "autolesao", "abuso", "extremo_financeiro"}


def carregar_roteiro(caminho: Path = ARQUIVO_ROTEIRO) -> dict:
    """Lê e valida: toda fala tem id único, estágio conhecido e texto; variável citada existe."""
    roteiro = json.loads(Path(caminho).read_text(encoding="utf-8"))
    ids, problemas = set(), []
    for fala in roteiro["falas"]:
        fid = fala.get("id")
        if not fid:
            problemas.append(f"fala sem id: {fala!r:.60}")
            continue
        if fid in ids:
            problemas.append(f"id duplicado: {fid}")
        ids.add(fid)
        if fala.get("estagio") not in roteiro["estagios"]:
            problemas.append(f"{fid}: estágio desconhecido {fala.get('estagio')!r}")
        if not fala.get("texto"):
            problemas.append(f"{fid}: sem texto")
        for variavel in fala.get("variaveis", []):
            if variavel not in roteiro["variaveis"]:
                problemas.append(f"{fid}: variável sem fonte declarada {variavel!r}")
        if fala.get("estagio") == "extremo":
            # Encaminhamento em extremos (docs/contrato-api-frontend.md §4.9): texto fixo, nunca visível como aviso.
            if fala.get("destino") not in DESTINOS_EXTREMO:
                problemas.append(f"{fid}: extremo sem destino válido {fala.get('destino')!r}")
            if fala.get("motivo") not in MOTIVOS_EXTREMO:
                problemas.append(f"{fid}: extremo sem motivo válido {fala.get('motivo')!r}")
            if fala.get("visivel") is not False:
                problemas.append(f"{fid}: extremo precisa de visivel=false")
            if fala.get("motivo") == "ameaca" and fala.get("destino") != "seguranca":
                problemas.append(f"{fid}: ameaça vai para segurança, não {fala.get('destino')!r}")
    if problemas:
        raise ValueError("Roteiro inválido: " + "; ".join(problemas))
    return roteiro


class ControleConversaAPI(APIView):
    def get(self, request):
        roteiro = carregar_roteiro()
        estagio = request.GET.get("estagio")
        if estagio:
            if estagio not in roteiro["estagios"]:
                return Response({"erro": f"Estágio desconhecido: {estagio!r}. Válidos: {roteiro['estagios']}."},
                                status=status.HTTP_400_BAD_REQUEST)
            roteiro = {**roteiro, "falas": [f for f in roteiro["falas"] if f["estagio"] == estagio]}
        # Formato pedido pelo front (falas-fixas.md): cada fala leva {id, estagio, texto, variaveis[], versao_roteiro}.
        # Aditivo: os campos antigos (versao no topo, demais chaves da fala) continuam.
        versao = roteiro["versao"]
        falas = [{**f, "variaveis": f.get("variaveis", []), "versao_roteiro": versao} for f in roteiro["falas"]]
        return Response({**roteiro, "versao_roteiro": versao, "falas": falas, "total_falas": len(falas)},
                        status=status.HTTP_200_OK)
