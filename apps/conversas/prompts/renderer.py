"""Only checked-in templates; no user-supplied template names or variables.

Portado de agente-app-mobile/agent_backend (commit 1302ba5). Mudança: o prompt `system` pode receber o
`titular` da sessão (pessoa, código, gênero do CSV da verdade). Esses valores vêm do servidor, nunca da
mensagem, e são validados por forma antes de entrar no template (prova negativa em tests/test_conversas_prompts.py).
"""
import hashlib
import re
from datetime import date
from pathlib import Path
from liquid import DictLoader, Environment, StrictUndefined

ROOT = Path(__file__).parent
NAMES = ('system', 'input_guard', 'output_guard')
PARTIALS = ('capabilities', 'financial_distinctions', 'institutional_policy', 'spending_projection',
            'identidade', 'dados_titular')
PADRAO_PESSOA = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ' -]{0,39}")
PADRAO_CODIGO = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')


def titular_para_prompt(titular):
    """Valida o titular (dict do perfil_usuario) e devolve só pessoa (nome_gerado do mesmo id) e código. Forma
    inválida: ValueError. Regra do dono (2026-09-27 10:22): gênero NUNCA entra no prompt."""
    if titular is None:
        return None
    pessoa, codigo = (titular.get(k) if isinstance(titular, dict) else None for k in ('pessoa', 'codigo'))
    if not (isinstance(pessoa, str) and PADRAO_PESSOA.fullmatch(pessoa)):
        raise ValueError('Titular: pessoa fora do formato')
    if not (isinstance(codigo, str) and PADRAO_CODIGO.fullmatch(codigo)):
        raise ValueError('Titular: código fora do formato')
    return {'pessoa': pessoa, 'codigo': codigo}


def render_prompt(name, *, reference_date, titular=None):
    if name not in NAMES:
        raise ValueError('Template not allowed')
    date.fromisoformat(reference_date)
    dados_titular = titular_para_prompt(titular) if name == 'system' else None
    # DictLoader exposes only a fixed list: filesystem traversal is not possible.
    templates = {n: (ROOT / f'{n}.liquid').read_text(encoding='utf-8') for n in NAMES}
    templates.update({f'partials/{n}': (ROOT / 'partials' / f'{n}.liquid').read_text(encoding='utf-8')
                      for n in PARTIALS})
    env = Environment(loader=DictLoader(templates), undefined=StrictUndefined, strict_filters=True)
    env.loop_iteration_limit = 100
    env.output_stream_limit = 16000
    text = env.get_template(name).render(policy_version='1.0', reference_date=reference_date,
                                         titular=dados_titular)
    if len(text) > 16000:
        raise ValueError('Prompt budget exceeded')
    return text, hashlib.sha256(text.encode()).hexdigest()


# Acréscimo (2026-09-27, rota conversas/interacao/): instrução por etapa com bloco de contexto estruturado.
# Fora de NAMES de propósito: render_prompt('interacao') continua recusado; as variáveis vêm só do servidor
# (apps/conversas/interacao.py), nunca da mensagem do cliente, que vai em `data`, não no template.
NAMES_INTERACAO = ('interacao',)


def render_interacao(**variaveis):
    template = (ROOT / 'interacao.liquid').read_text(encoding='utf-8')
    env = Environment(loader=DictLoader({'interacao': template}), undefined=StrictUndefined, strict_filters=True)
    env.loop_iteration_limit = 100
    env.output_stream_limit = 16000
    text = env.get_template('interacao').render(**variaveis)
    if len(text) > 16000:
        raise ValueError('Prompt budget exceeded')
    return text, hashlib.sha256(text.encode()).hexdigest()
