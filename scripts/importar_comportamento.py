"""Importa a base de calibragem de comportamento para desafio_itau/politica/comportamento-v1.json.

Uso (da raiz do repo):
    python scripts/importar_comportamento.py "C:/Users/ACER/Desktop/Perguntas e Respostas.txt"
    python scripts/importar_comportamento.py <fonte> --seco      # só valida e imprime achados, não grava

- Extrai TODO array JSON de objetos com `id` do arquivo-fonte (o texto pode ter prosa em volta); não reescreve dados.
- Valida cada caso pelo schema de comportamento.py; se algum falhar, NÃO grava e lista os ids e erros.
- Calcula achados (comportamento.auditar) e grava `achados` + `alerta` por caso; o dado original não é corrigido.
- Se já existir uma versão, arquiva a antiga em archive/<data>/desafio_itau/politica/ e sobe a versão menor.
"""
import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ), str(RAIZ / 'tests')]
import conversas_apoio  # noqa: E402,F401  (django.setup, como os testes)
from desafio_itau.politica import comportamento  # noqa: E402

DESCRICAO = ('perguntas e respostas para aumentar a calibragem; fornecido pelo dono na sessao 2026-09-27 ~09:53 BRT, '
             'nao homologado')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fonte')
    ap.add_argument('--seco', action='store_true')
    args = ap.parse_args()
    fonte = Path(args.fonte)
    bruto = fonte.read_bytes()
    agora = datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%Y-%m-%d %H:%M BRT')
    casos = comportamento.extrair_casos(bruto.decode('utf-8-sig'))
    ids = [c['id'] for c in casos]
    print(f'casos extraidos: {len(casos)} · {fonte.name} · {agora}')
    print(f'ids 1..N contiguos: {ids == list(range(1, len(ids) + 1))}; repetidos: {sorted({i for i in ids if ids.count(i) > 1})}')

    erros = {}
    for c in casos:
        try:
            comportamento.Caso.model_validate(c)
        except ValueError as e:
            erros[c.get('id')] = str(e).splitlines()[:6]
    if erros:
        print(f'SCHEMA REPROVOU {len(erros)} casos; nada gravado:')
        print(json.dumps(erros, ensure_ascii=False, indent=1)[:6000])
        return 2

    achados, alertas = comportamento.auditar(casos)
    anterior = json.loads(comportamento.ARQUIVO.read_text(encoding='utf-8')) if comportamento.ARQUIVO.exists() else None
    if anterior:
        ma, mi, _ = map(int, anterior['versao'].split('.'))
        versao, historico = f'{ma}.{mi + 1}.0', anterior['historico']
    else:
        versao, historico = '1.0.0', []
    historico = historico + [f'{versao} ({agora}): {len(casos)} casos importados de {fonte.name} '
                             f'(sha256 {hashlib.sha256(bruto).hexdigest()[:12]}); achados registrados, dados nao corrigidos.']
    base = {
        'schema_version': '1.0', 'id': 'comportamento-i-agora', 'versao': versao, 'natureza': 'dado_de_calibragem',
        'status': 'NAO_HOMOLOGADO',
        'fonte': {'descricao': DESCRICAO, 'arquivo': str(fonte), 'sha256': hashlib.sha256(bruto).hexdigest(),
                  'lido_em': agora},
        'historico': historico, 'achados': achados,
        'casos': [{**c, 'alerta': alertas.get(c['id'], [])} for c in casos],
    }
    comportamento.validar(base)
    print(json.dumps({'versao': versao, 'achados': achados}, ensure_ascii=False, indent=1)[:12000])
    print(f'casos com alerta: {len(alertas)} de {len(casos)}')
    if args.seco:
        return 0
    if anterior:
        destino = RAIZ / 'archive' / agora[:10] / comportamento.ARQUIVO.relative_to(RAIZ)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(comportamento.ARQUIVO, destino.with_name(f'comportamento-v1.{anterior["versao"]}.json'))
    comportamento.ARQUIVO.write_text(json.dumps(base, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'gravado {comportamento.ARQUIVO.relative_to(RAIZ)} versao {versao}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
