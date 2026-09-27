"""Primeira interação: escolhe 1 dos 1.000 clientes, aplica as regras implementadas e chama a API.

Uso (a partir da pasta do Django):
  PYTHONPATH=. ../.venv/Scripts/python.exe scripts/primeira_interacao.py [--semente N] [--cliente ID] [--chamar-google]
Sem --chamar-google não há chamada de rede; as rotas que dependem da Google ficam NAO_MEDIDO.
"""
import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone, timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")
import django  # noqa: E402

django.setup()
from django.test import Client  # noqa: E402
from desafio_itau.segredos import obter_api_key  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--semente", type=int, default=20260927)
p.add_argument("--cliente", type=int)
p.add_argument("--chamar-google", action="store_true")
a = p.parse_args()

cliente_id = a.cliente or random.Random(a.semente).randint(1, 1000)
c = Client(raise_request_exception=False)
brt = timezone(timedelta(hours=-3))
out = {
    "gerado_em": datetime.now(brt).isoformat(timespec="seconds"),
    "escolha": {"cliente_id": cliente_id, "metodo": "fixado" if a.cliente else f"random.Random({a.semente}).randint(1,1000)"},
}


def get(url):
    r = c.get(url)
    return r.status_code, r.json()


def post(url, corpo):
    r = c.post(url, data=json.dumps(corpo), content_type="application/json")
    return r.status_code, r.json()


s, cliente = get(f"/api/v1/cliente/{cliente_id}/")
out["cliente"] = {"http": s, "dados": cliente}
s, ctx = get(f"/api/v1/contexto-score/{cliente_id}/")
out["regra_indice"] = {"http": s, "dados": ctx}
s, eagora = get(f"/api/v1/comunicacao/e-agora/{cliente_id}/")
out["regra_template_3"] = {"http": s, "dados": eagora}
s, chave = get("/api/v1/chave-interacao-tela-iai/")
out["chave_on_off"] = {"http": s, "estado": chave.get("estado")}
s, v1 = get(f"/api/v1/chat/variavel-1/{cliente_id}/")
out["variavel_1"] = {"http": s, "texto_ativo": (v1.get("chat_variavel_1") or {}).get("texto_ativo")}

_, origem = obter_api_key()
out["chave_api"] = {"origem": origem or "AUSENTE"}

if a.chamar_google and origem:
    s, st = get("/api/v1/context-agent/status-harness/?validar=1")
    out["status_harness_validado"] = {"http": s, "resumo": json.dumps(st, ensure_ascii=False)[:0] or None}
    def achar(o):
        if isinstance(o, dict):
            if "validacao" in o or "secret_mascarado" in o:
                return {k: o[k] for k in o if k in ("status", "variavel_identificada", "secret_mascarado", "validacao")}
            for v in o.values():
                r = achar(v)
                if r:
                    return r
    out["status_harness_validado"]["resumo"] = achar(st)
    s, pc = post("/api/v1/context-agent/primeira-chamada/", {"texto_inicial": "Olá! Em uma frase, o que é uma reserva de emergência?"})
    out["primeira_chamada"] = {"http": s, "dados": pc}
    nome = (cliente.get("nome") if isinstance(cliente, dict) else None)
    corpo = {"mensagem": "Tenho um dinheiro parado, onde posso guardar?", "cliente_id": cliente_id}
    if nome:
        corpo["cliente_nome"] = nome
    s, em = post("/api/v1/context-agent/enviar-mensagem/", corpo)
    out["enviar_mensagem"] = {"http": s, "dados": em}
else:
    motivo = "sem chave (API_KEY_SECRECT ausente no ambiente e no .secrets)" if not origem else "sem --chamar-google"
    for k in ("status_harness_validado", "primeira_chamada", "enviar_mensagem"):
        out[k] = {"NAO_MEDIDO": motivo}

json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
