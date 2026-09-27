"""Envia uma construção ao Gemini como REVISOR e grava a resposta selada.

Uso (da raiz deste repo):
    ..\\.venv\\Scripts\\python.exe scripts\\revisao_gemini.py --titulo "<o que se pede>" <arquivo> [<arquivo> ...]

A chave é lida por desafio_itau.segredos.obter_api_key (a mesma da primeira chamada) e nunca é impressa.
Saída: relatorios/revisao-gemini/<AAAA-MM-DDTHHMM>.json com modelo, hora BRT, sha256 e bytes de cada
arquivo enviado, tempo medido e a resposta estruturada. Falha de rede, cota ou chave: NAO_MEDIDO, nada gravado.
O Gemini é revisor, não juiz: o veredito dele é uma opinião a conferir, nunca aprovação automática.
"""

import argparse
import hashlib
import importlib.util
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from desafio_itau.modelos_llm import MODELO_PRIMEIRA_CHAMADA  # noqa: E402
from desafio_itau.segredos import obter_api_key  # noqa: E402

MODELO = MODELO_PRIMEIRA_CHAMADA  # fonte única; gemini-2.5-flash-lite dá 404 a chaves novas (2026-09-27)
BRT = timezone(timedelta(hours=-3))
LIMITE_BYTES = 200_000

INSTRUCAO = """Você é revisor técnico independente. Revise a construção abaixo (código, SQL, skills e plano).
Responda SÓ JSON com as chaves:
  "veredito": "APROVADO" | "AJUSTAR" | "REPROVADO",
  "resumo": string curta,
  "achados": [{"arquivo": string, "severidade": "alta"|"media"|"baixa", "problema": string, "sugestao": string}],
  "lacunas_de_prova": [string],   // afirmações sem teste ou medição que as sustente
  "perguntas_ao_dono": [string]
Cite só o que está nos arquivos. Se não souber, diga que não sabe; não invente números."""


def montar(titulo: str, arquivos: list[Path]) -> tuple[str, list[dict]]:
    partes, selos = [f"# Pedido: {titulo}\n"], []
    for arq in arquivos:
        dados = arq.read_bytes()
        try:
            nome = arq.resolve().relative_to(RAIZ).as_posix()
        except ValueError:
            nome = arq.resolve().as_posix()
        selos.append({"arquivo": nome, "bytes": len(dados), "sha256": hashlib.sha256(dados).hexdigest()})
        partes.append(f"\n=== ARQUIVO: {arq.name} ===\n{dados.decode('utf-8', errors='replace')}")
    return "".join(partes), selos


def chamar(prompt: str, chave: str) -> tuple[dict, int]:
    corpo = json.dumps({
        "systemInstruction": {"parts": [{"text": INSTRUCAO}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }).encode("utf-8")
    pedido = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent",
        data=corpo, headers={"Content-Type": "application/json", "x-goog-api-key": chave}, method="POST")
    inicio = time.perf_counter()
    with urllib.request.urlopen(pedido, timeout=120) as resposta:
        bruto = json.loads(resposta.read().decode("utf-8"))
    ms = round((time.perf_counter() - inicio) * 1000)
    texto = bruto["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(texto), ms


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--titulo", required=True)
    ap.add_argument("arquivos", nargs="+", type=Path)
    args = ap.parse_args()
    prompt, selos = montar(args.titulo, args.arquivos)
    if len(prompt.encode("utf-8")) > LIMITE_BYTES:
        print(f"NAO_MEDIDO: pedido com {len(prompt.encode('utf-8'))} bytes > limite {LIMITE_BYTES}")
        return 2
    chave, origem_chave = obter_api_key()
    if not chave:
        print("NAO_MEDIDO: API_KEY_SECRECT ausente (.secrets ou ambiente)")
        return 2
    try:
        revisao, ms = chamar(prompt, chave)
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError) as erro:
        detalhe = erro.code if isinstance(erro, urllib.error.HTTPError) else type(erro).__name__
        print(f"NAO_MEDIDO: Gemini não respondeu uma revisão válida ({detalhe})")
        return 2
    agora = datetime.now(BRT)
    saida = RAIZ / "relatorios" / "revisao-gemini" / f"{agora.strftime('%Y-%m-%dT%H%M')}.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    registro = {"modelo": MODELO, "medido_em": agora.strftime("%Y-%m-%dT%H:%M BRT"), "titulo": args.titulo,
                "origem_chave": origem_chave, "tempo_resposta_ms": ms, "bytes_enviados": len(prompt.encode("utf-8")), "arquivos": selos,
                "papel": "revisor (opinião a conferir, não aprovação)", "revisao": revisao}
    saida.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{revisao.get('veredito')} em {ms} ms, {len(revisao.get('achados', []))} achados -> {saida.relative_to(RAIZ)}")
    modulo = verificador()
    if modulo is None:
        print("NAO_VERIFICADO: skill revisao-gemini ausente (.claude/skills/revisao-gemini)")
        return 0
    falhas = modulo.verificar(registro)
    for falha in falhas:
        print(f"FALHA do registro: {falha}")
    return 1 if falhas else 0


def verificador():
    """O verificador da skill revisao-gemini (.claude/skills/revisao-gemini/tools/verificar-revisao.py)."""
    ferramentas = RAIZ / ".claude" / "skills" / "revisao-gemini" / "tools"
    if not (ferramentas / "verificar-revisao.py").is_file():
        return None
    sys.path.insert(0, str(ferramentas))
    spec = importlib.util.spec_from_file_location("verificar_revisao", ferramentas / "verificar-revisao.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


if __name__ == "__main__":
    sys.exit(main())
