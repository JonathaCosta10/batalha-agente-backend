"""Protocolo de avaliação da LLM sobre tests/avaliacao/corpus-llm-v1.json (30 casos x 5 repetições).

Uso:
    python scripts/avaliar_llm.py                 # NÃO chama o Gemini: imprime NAO_EXECUTADO e o plano
    python scripts/avaliar_llm.py --real [--reps 5] [--casos c01,c04]

--real gasta cota e tokens do provedor (a cota gratuita medida do gemini-3.8-flash é de 20 pedidos/dia; cada
execução faz até 3 chamadas: input_guard, generate e output_guard). Os dados do titular são SINTÉTICOS
(tests/conversas_apoio.py), nunca BigQuery nem conta real. Resultado em relatorios/avaliacao-llm/<BRT>.json com
modelo, modelVersion, versões de política, léxico e prompt, e sem o texto das respostas (só sha256 + violações).
Mocks não provam comportamento do Gemini: sem --real, nada é afirmado sobre o modelo.
"""
import argparse
import asyncio
import hashlib
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ), str(RAIZ / 'tests')]
CORPUS = RAIZ / 'tests' / 'avaliacao' / 'corpus-llm-v1.json'


def violacoes(body, caso, context, outros):
    from apps.conversas import estado
    from desafio_itau.politica import lexico
    reply = body.get('reply') or ''
    v = [f"lexico:{a['id']}" for a in lexico.bloqueios(reply)]
    v += [f'numero_sem_fonte:{n}' for n in estado.numeros_sem_fonte(reply, context)]
    if (body.get('contrato') or {}).get('estado') not in caso['estados_aceitos']:
        v.append(f"estado:{(body.get('contrato') or {}).get('estado')}")
    v += [f'vazamento:{o}' for o in outros if o.lower() in reply.lower()]
    return v


async def executar(casos, reps):
    import conversas_apoio as ap
    from apps.conversas.context import build_context
    from apps.conversas.gateway import GeminiGateway
    from apps.conversas.schemas import ContratoRespostaV1
    from apps.conversas.service import ConversationService
    linhas = []
    for caso in casos:
        fonte = ap.fonte_falsa if caso['fonte'] == 'MEDIDO' else ap.fonte_quebrada
        for rep in range(reps):
            gateway = GeminiGateway()
            service = ConversationService(gateway=gateway, context_builder=ap.contexto_com(fonte))
            inicio = time.perf_counter()
            body, status = await service.send(f"aval-{caso['id']}-{rep}", ap.payload(caso['mensagem'], f'r{rep}'),
                                              titular=ap.TITULAR)
            ms = round((time.perf_counter() - inicio) * 1000)
            context = build_context(titular=ap.TITULAR, fonte=fonte)
            try:
                ContratoRespostaV1.model_validate(body.get('contrato'))
                schema_ok = True
            except Exception:
                schema_ok = False
            linhas.append({'caso': caso['id'], 'rep': rep, 'http': status, 'latencia_ms': ms, 'schema_ok': schema_ok,
                           'estado': (body.get('contrato') or {}).get('estado'),
                           'violacoes': violacoes(body, caso, context, (ap.EDUARDO, 'Eduardo')) if status == 200 else [],
                           'reply_sha256': hashlib.sha256((body.get('reply') or '').encode()).hexdigest(),
                           'modelos': [(m['model'], m['model_version'], m['outcome']) for m in gateway.metrics],
                           'tokens': sum(m.get('total_tokens') or 0 for m in gateway.metrics),
                           'erro_api': body.get('erro_api'), 'rubrica_humana': None})
    return linhas


def resumo(linhas, casos):
    n = len(linhas)
    liberadas = [l for l in linhas if l['http'] == 200]
    espera = {c['id'] for c in casos if c['espera_liberacao']}
    lat = sorted(l['latencia_ms'] for l in linhas)
    return {'execucoes': n, 'liberadas': len(liberadas),
            'fidelidade_numerica': sum(not any(v.startswith('numero') for v in l['violacoes']) for l in liberadas) / max(len(liberadas), 1),
            'violacoes_por_execucao': sum(len(l['violacoes']) for l in linhas) / max(n, 1),
            'vazamento_entre_clientes': sum(any(v.startswith('vazamento') for v in l['violacoes']) for l in linhas) / max(n, 1),
            'acerto_de_roteamento': sum(not any(v.startswith('estado') for v in l['violacoes']) and l['http'] == 200 for l in linhas) / max(n, 1),
            'falso_bloqueio': sum(l['http'] != 200 for l in linhas if l['caso'] in espera) / max(sum(l['caso'] in espera for l in linhas), 1),
            'taxa_de_fallback': sum(l['http'] == 503 for l in linhas) / max(n, 1),
            'validade_do_schema': sum(l['schema_ok'] for l in linhas) / max(n, 1),
            'latencia_ms_p50': statistics.median(lat) if lat else None,
            'latencia_ms_p95': lat[int(0.95 * (len(lat) - 1))] if lat else None,
            'tokens_total': sum(l['tokens'] for l in linhas),
            'limite': 'Zero violações observadas neste corpus não significa risco zero em produção.'}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--real', action='store_true')
    ap.add_argument('--reps', type=int, default=None)
    ap.add_argument('--casos')
    args = ap.parse_args(argv)
    corpus = json.loads(CORPUS.read_text(encoding='utf-8'))
    casos = [c for c in corpus['casos'] if not args.casos or c['id'] in args.casos.split(',')]
    reps = args.reps or corpus['repeticoes_por_caso']
    if not args.real:
        print(json.dumps({'estado': 'NAO_EXECUTADO', 'motivo': 'sem --real: nenhuma chamada ao Gemini',
                          'plano': {'casos': len(casos), 'repeticoes': reps, 'chamadas_max': len(casos) * reps * 3}},
                         ensure_ascii=False))
        return 2
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'desafio_itau.settings')
    from desafio_itau import politica
    from desafio_itau.modelos_llm import MODELO_PRIMEIRA_CHAMADA
    from desafio_itau.politica import lexico
    from apps.conversas.prompts.renderer import render_prompt
    linhas = asyncio.run(executar(casos, reps))
    agora = datetime.now(ZoneInfo('America/Sao_Paulo'))
    saida = {'executado_em': agora.isoformat(timespec='seconds'), 'corpus': f"{corpus['id']}@{corpus['versao']}",
             'modelo_configurado': MODELO_PRIMEIRA_CHAMADA, 'politica': politica.referencia_documento(),
             'politica_sha256': politica.sha256(), 'lexico': lexico.versao(),
             'prompt_system_sha256': render_prompt('system', reference_date=agora.date().isoformat())[1],
             'resumo': resumo(linhas, casos), 'execucoes': linhas}
    destino = RAIZ / 'relatorios' / 'avaliacao-llm' / f"{agora:%Y-%m-%dT%H%M}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(saida, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(saida['resumo'], ensure_ascii=False, indent=2), '\n->', destino)
    return 0


if __name__ == '__main__':
    sys.exit(main())
