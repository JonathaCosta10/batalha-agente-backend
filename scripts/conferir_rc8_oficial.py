"""Confere a base local da RC nº 8/2023 contra o texto servido pela API pública do BCB.

Uso:  python scripts/conferir_rc8_oficial.py [--arquivo <json já baixado>] [--saida <relatorio.json>]

Sem --arquivo, baixa https://www.bcb.gov.br/api/conteudo/app/normativos/exibenormativo (p1=Resolução Conjunta,
p2=8). Compara cada artigo de apps/conversas/knowledge/resolucao-conjunta-08-2023.json com o texto oficial, após
remover HTML e normalizar espaços (NFC). Igualdade após normalização prova coincidência textual com o que o BCB
serviu na data da consulta; não é certificação jurídica nem cobre a diagramação oficial.
Sem rede: estado NAO_MEDIDO, nada é afirmado.
"""
import argparse
import hashlib
import html
import json
import re
import sys
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parents[1]
BASE = RAIZ / 'apps' / 'conversas' / 'knowledge' / 'resolucao-conjunta-08-2023.json'
URL = ('https://www.bcb.gov.br/api/conteudo/app/normativos/exibenormativo'
       '?p1=Resolu%C3%A7%C3%A3o%20Conjunta&p2=8')


def normalizar(texto):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', texto)).strip()


def texto_oficial(bruto):
    dados = json.loads(bruto)
    item = dados['conteudo'][0] if isinstance(dados, dict) and 'conteudo' in dados else dados
    meta = {k: item.get(k) for k in ('Tipo', 'Numero', 'Data', 'Assunto', 'Responsavel', 'Situacao', 'Revogado',
                                     'Cancelado') if k in item}
    texto = html.unescape(re.sub(r'<[^>]+>', ' ', item.get('Texto') or ''))
    return meta, normalizar(texto)


def comparar(base, oficial):
    linhas = []
    for artigo in base['artigos']:
        local = normalizar(artigo['texto'])
        if local and local in oficial:
            resultado = 'IGUAL_AO_OFICIAL'
        elif local and re.sub(r'\s', '', local) in re.sub(r'\s', '', oficial):
            # A troca de tags HTML por espaço cria espaços que o texto local não tem; letras e sinais coincidem.
            resultado = 'IGUAL_SALVO_ESPACOS'
        else:
            resultado = 'DIVERGE'
        linhas.append({'id': artigo['id'], 'resultado': resultado,
                       'chars': len(local), 'sha256_local': hashlib.sha256(local.encode()).hexdigest()})
    return linhas


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--arquivo')
    ap.add_argument('--saida')
    args = ap.parse_args(argv)
    agora = datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(timespec='seconds')
    try:
        bruto = Path(args.arquivo).read_bytes() if args.arquivo else urllib.request.urlopen(URL, timeout=30).read()
    except Exception as erro:  # sem rede ou arquivo: não mediu
        print(json.dumps({'estado': 'NAO_MEDIDO', 'motivo': type(erro).__name__, 'consultado_em': agora}))
        return 2
    meta, oficial = texto_oficial(bruto)
    base = json.loads(BASE.read_text(encoding='utf-8'))
    relatorio = {'estado': 'MEDIDO', 'fonte': URL if not args.arquivo else args.arquivo, 'consultado_em': agora,
                 'sha256_resposta_bruta': hashlib.sha256(bruto).hexdigest(), 'metadados_oficiais': meta,
                 'base_local': str(BASE.relative_to(RAIZ)).replace('\\', '/'),
                 'artigos': comparar(base, oficial),
                 'limitacao': 'Coincidência textual após normalização de espaços; não é certificação jurídica.'}
    saida = json.dumps(relatorio, ensure_ascii=False, indent=2)
    if args.saida:
        Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
        Path(args.saida).write_text(saida + '\n', encoding='utf-8')
    print(saida)
    return 0 if all(a['resultado'] != 'DIVERGE' for a in relatorio['artigos']) else 1


if __name__ == '__main__':
    sys.exit(main())
