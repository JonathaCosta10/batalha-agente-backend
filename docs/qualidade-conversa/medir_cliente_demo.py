r"""Pergunta dirigida ao fluxo da demo e mede tempo e consistência factual.

Uso (na raiz Django): ..\.venv\Scripts\python.exe docs/qualidade-conversa/medir_cliente_demo.py 1
Não chama LLM nem consulta a base BigQuery. O ID aqui é o do cliente da demo.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")
import django  # noqa: E402

django.setup()
from django.test import Client  # noqa: E402
from apps.context_agent_datadriven.services.qualidade_fluxo import verificar_fluxo  # noqa: E402


BRT = timezone(timedelta(hours=-3))


def medir(cliente_id):
    inicio_total = perf_counter()
    api = Client()
    rotas = {
        "cliente": f"/api/v1/cliente/{cliente_id}/",
        "chat": f"/api/v1/chat/variavel-1/{cliente_id}/",
        "e_agora": f"/api/v1/comunicacao/e-agora/{cliente_id}/",
    }
    respostas = {}
    tempos = {}
    for nome, rota in rotas.items():
        inicio = perf_counter()
        resposta = api.get(rota)
        tempos[nome] = round((perf_counter() - inicio) * 1000, 2)
        if resposta.status_code != 200:
            raise RuntimeError(f"NAO_MEDIDO: {rota} respondeu HTTP {resposta.status_code}.")
        respostas[nome] = resposta.json()

    cliente, chat, comunicacao = (respostas[n] for n in ("cliente", "chat", "e_agora"))
    checks = verificar_fluxo(cliente, chat, comunicacao)
    if not all(checks.values()):
        raise RuntimeError(f"REPROVADO: controles factuais {checks}")

    ativos = [item for item in comunicacao["planilha_fixa"]
              if item["status_elegibilidade"] == "Pré-Aprovado"]
    trecho_elegibilidade = ("nenhum aparece como Pré-Aprovado" if not ativos else
                            f"{len(ativos)} {'aparece' if len(ativos) == 1 else 'aparecem'} como Pré-Aprovado")
    resposta_curta = (
        f"{cliente['primeiro_nome']} vê a conversa em modo {chat['modo_ativo']} "
        f"({chat['chat_variavel_1']['texto_ativo']['tag']}). Ao tocar em 'E agora?', "
        f"o Template 3 apresenta {len(comunicacao['planilha_fixa'])} produtos; "
        f"{trecho_elegibilidade}."
    )
    return {
        "pergunta": f"Qual é o fluxo do cliente {cliente_id} da conversa até 'E agora?'?",
        "resposta": resposta_curta,
        "estado": "COMPROVADO_NA_DEMO",
        "fonte_oficial": "db.sqlite3 + TemplateEngine do backend Django",
        "id_cliente_demo": cliente_id,
        "medido_em": datetime.now(BRT).isoformat(),
        "tempo_rotas_ms": tempos,
        "tempo_total_ms": round((perf_counter() - inicio_total) * 1000, 2),
        "controles_factuais": checks,
        "evidencias": rotas,
        "resposta_llm": "NAO_MEDIDO: este teste não chama LLM",
        "vinculo_com_bigquery": "NAO_VERIFICADO: a demo usa ID inteiro; o extrato usa UUID",
    }


if __name__ == "__main__":
    numero = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    destino = Path(f"docs/qualidade-conversa/medicoes/{datetime.now(BRT):%Y-%m-%d}/cliente_{numero}.json")
    try:
        resultado = medir(numero)
    except Exception as erro:
        print(str(erro), file=sys.stderr)
        sys.exit(1)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{resultado['estado']}: {resultado['tempo_total_ms']} ms -> {destino}")
