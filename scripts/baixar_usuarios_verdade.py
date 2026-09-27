"""
Baixa o CSV da verdade dos usuários: DISTINCT id_usuario do extrato no BigQuery (ADC),
mais duas colunas inventadas, `nome` (primeiro nome) e `genero` (F ou M).

A base não tem nome nem gênero; os dois são sorteados com semente fixa, para o mesmo
id_usuario receber sempre o mesmo nome. O índice 1 é fixado como "Maria" (F): é o
usuário da primeira conferência ("quem sou eu" -> Código = id_usuario, pessoa = Maria).

Saída:
  data/usuarios_verdade.csv        indice,id_usuario,nome,genero,movimentos,meses,primeiro_anomes,ultimo_anomes
  data/usuarios_verdade.selo.json  fonte, job, hora BRT, semente, total e sha256 do CSV

Uso (na pasta backend-agente-conversacional):
  ..\\frontend-agent-conversacional\\.venv\\Scripts\\python.exe scripts\\baixar_usuarios_verdade.py
"""

import csv
import hashlib
import json
import os
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")

import django  # noqa: E402

django.setup()

from apps.context_agent_datadriven.services import usuario_real  # noqa: E402

SEMENTE = "organizesee-usuarios-verdade-v1"
PRIMEIRO_USUARIO = ("Maria", "F")
NOMES = {
    "F": ["Ana", "Beatriz", "Camila", "Daniela", "Eduarda", "Fernanda", "Gabriela", "Helena",
          "Isabela", "Juliana", "Larissa", "Luana", "Mariana", "Natália", "Patrícia", "Rafaela",
          "Sofia", "Tatiane", "Valentina", "Vitória", "Aline", "Bruna", "Carolina", "Letícia"],
    "M": ["Arthur", "Bruno", "Carlos", "Daniel", "Eduardo", "Felipe", "Gabriel", "Gustavo",
          "Henrique", "João", "Lucas", "Mateus", "Nicolas", "Otávio", "Pedro", "Rafael",
          "Samuel", "Thiago", "Vinícius", "Leonardo", "André", "Diego", "Marcelo", "Rodrigo"],
}
COLUNAS = ["indice", "id_usuario", "nome", "genero", "movimentos", "meses", "primeiro_anomes", "ultimo_anomes"]


def sortear(usuarios: list) -> list:
    """Uma linha por id_usuario, com nome e gênero sorteados de forma estável."""
    sorteio = random.Random(SEMENTE)
    linhas, vistos = [], set()
    for usuario in usuarios:
        if usuario["id_usuario"] in vistos:
            continue
        vistos.add(usuario["id_usuario"])
        genero = sorteio.choice("FM")
        nome = sorteio.choice(NOMES[genero])
        if int(usuario["indice"]) == 1:
            nome, genero = PRIMEIRO_USUARIO
        linhas.append({**{c: usuario.get(c) for c in COLUNAS}, "nome": nome, "genero": genero})
    return linhas


def main() -> int:
    try:
        lista = usuario_real.listar_usuarios()
    except (usuario_real.FonteIndisponivel, usuario_real.UsuarioRealDesligado) as erro:
        print(json.dumps({"estado": "NAO_MEDIDO", "erro": str(erro)}, ensure_ascii=False))
        return 1

    linhas = sortear(lista["usuarios"])
    destino = RAIZ / "data"
    destino.mkdir(exist_ok=True)
    arquivo = destino / "usuarios_verdade.csv"
    with arquivo.open("w", newline="", encoding="utf-8") as saida:
        escritor = csv.DictWriter(saida, fieldnames=COLUNAS)
        escritor.writeheader()
        escritor.writerows(linhas)

    selo = {
        **lista["selo"],
        "arquivo": "data/usuarios_verdade.csv",
        "total": len(linhas),
        "semente": SEMENTE,
        "colunas_inventadas": ["nome", "genero"],
        "sha256": hashlib.sha256(arquivo.read_bytes()).hexdigest(),
    }
    (destino / "usuarios_verdade.selo.json").write_text(json.dumps(selo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"total": len(linhas), "primeiro": linhas[0], "selo": selo}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
