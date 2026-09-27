"""
Leitura da chave do agente a partir do arquivo `.secrets` na raiz da solução.

Ordem de busca de `obter_api_key()`:
1. variável de ambiente API_KEY_SECRECT
2. API_KEY_SECRECT no arquivo `.secrets` (raiz da solução, ao lado do package.json)
3. legado: GEMINI_API_KEY, GSCONSOLE_SECRET, GOOGLE_API_KEY

O caminho do arquivo pode ser sobreposto pela variável SECRETS_FILE. Sem ela, vale o
primeiro que existir: `.secrets` na pasta pai (layout antigo, front na raiz) ou
`frontend-agent-conversacional/.secrets` (layout hackton-1-itau, front e back irmãos).
Não se chama `secrets.py` para não esconder o módulo `secrets` da biblioteca padrão.
"""

import os
from pathlib import Path
from typing import Dict, Optional, Tuple

NOME_CHAVE = "API_KEY_SECRECT"
VARIAVEIS_LEGADO = ("GEMINI_API_KEY", "GSCONSOLE_SECRET", "GOOGLE_API_KEY")

# desafio_itau/ -> projeto Django -> raiz da solução
ARQUIVO_SEGREDOS = Path(__file__).resolve().parent.parent.parent / ".secrets"
# Layout 2026-09-27: backend-agente-conversacional/ e frontend-agent-conversacional/ lado a lado.
ARQUIVO_SEGREDOS_FRONT = ARQUIVO_SEGREDOS.parent / "frontend-agent-conversacional" / ".secrets"
CANDIDATOS_SEGREDOS = (ARQUIVO_SEGREDOS, ARQUIVO_SEGREDOS_FRONT)


def caminho_segredos() -> Path:
    if os.environ.get("SECRETS_FILE"):
        return Path(os.environ["SECRETS_FILE"])
    for candidato in CANDIDATOS_SEGREDOS:
        if candidato.is_file():
            return candidato
    return ARQUIVO_SEGREDOS


def ler_segredos(caminho: Path) -> Dict[str, str]:
    """Lê linhas `CHAVE=valor`; ignora vazias, comentários `#` e aspas envolventes."""
    try:
        linhas = Path(caminho).read_text(encoding="utf-8-sig").splitlines()
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return {}

    segredos = {}
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave = chave.strip()
        if chave.startswith("export "):
            chave = chave[len("export "):].strip()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        if chave:
            segredos[chave] = valor
    return segredos


def obter_api_key() -> Tuple[Optional[str], Optional[str]]:
    """Devolve (chave, origem). Sem chave: (None, None). A origem nunca contém o valor."""
    valor = os.environ.get(NOME_CHAVE)
    if valor:
        return valor, f"env:{NOME_CHAVE}"

    valor = ler_segredos(caminho_segredos()).get(NOME_CHAVE)
    if valor:
        return valor, f".secrets:{NOME_CHAVE}"

    for nome in VARIAVEIS_LEGADO:
        valor = os.environ.get(nome)
        if valor:
            return valor, f"env:{nome}"

    return None, None
