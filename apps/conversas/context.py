"""Small, explicit evidence collection; hashes prove integrity, not legal authenticity.

Portado de agente-app-mobile/agent_backend (commit 1302ba5). Mudança: a fixture
`financial_summary('1000.20', '1100.30')` saiu. Os fatos financeiros vêm do extrato do titular da
sessão no BigQuery (`services/usuario_real.perfil`), com o `selo` da medição. Se a fonte falhar ou
estiver desligada, o contexto declara NAO_MEDIDO/OFF e não leva número nenhum: nunca zero, nunca fixture.
"""
import hashlib
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

KNOWLEDGE = Path(__file__).parent / 'knowledge'
ORIGEM = 'bigquery_extrato'
# (id do fato, onde está no perfil de usuario_real, é valor em R$ com 2 casas?)
FATOS_EXTRATO = (
    ('essencial_mensal', ('visoes', 'perfil_t3', 'essencial_mensal'), True),
    ('compromisso_mensal', ('visoes', 'perfil_t3', 'compromisso_mensal'), True),
    ('discricionario_mensal', ('visoes', 'perfil_t3', 'discricionario_mensal'), True),
    ('taxa_surplus_pct', ('resumo', 'taxa_surplus_pct'), True),
    ('segmento_t3', ('resumo', 'segmento_t3'), False),
    ('meses_na_janela', ('resumo', 'meses_na_janela'), False),
    ('assinaturas_mensal', ('visoes', 'recorrencias', 'assinaturas_mensal'), True),
    ('pct_inflow_comprometido', ('visoes', 'dividas', 'pct_inflow_comprometido'), True),
    ('juros_pagos_total', ('visoes', 'dividas', 'juros_pagos_total'), True),
    ('maior_categoria_discricionaria', ('visoes', 'discricionario', 'maior_categoria_discricionaria'), False),
    ('maior_categoria_total', ('visoes', 'discricionario', 'maior_categoria_total'), True),
)


def financial_summary(inflows: str, outflows: str):
    if not all(isinstance(v, str) and re.fullmatch(r'\d{1,12}\.\d{2}', v) for v in (inflows, outflows)):
        raise ValueError('Use nonnegative decimal strings with two decimal places')
    return {'inflows': inflows, 'outflows': outflows,
            'cash_flow': str(Decimal(inflows) - Decimal(outflows)),
            'balance': None, 'debt': None, 'arrears': None, 'income': None}


def _dinheiro(valor):
    """float/int/str da base -> '1234.56'. None, bool, NaN ou texto: None (não medido, não zero)."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = Decimal(str(valor))
    except InvalidOperation:
        return None
    if not numero.is_finite():
        return None
    return str(numero.quantize(Decimal('0.01')))


def _pegar(origem, caminho):
    for chave in caminho:
        if not isinstance(origem, dict):
            return None
        origem = origem.get(chave)
    return origem


def fatos_do_titular(perfil):
    """Perfil de usuario_real -> (fatos, período). Sem inflow/outflow medidos: ValueError."""
    resumo = perfil.get('resumo') or {}
    entrada, saida = _dinheiro(resumo.get('inflow_mensal')), _dinheiro(resumo.get('outflow_mensal'))
    if entrada is None or saida is None or Decimal(entrada) < 0 or Decimal(saida) < 0:
        raise ValueError('Perfil sem inflow/outflow medidos')
    periodo = f"{resumo.get('meses_na_janela')} meses completos antes de {str(perfil.get('data_corte'))[:7]}"
    fatos = [{'id': k, 'value': v, 'origin': ORIGEM, 'period': periodo, 'unit': 'BRL/mes' if v is not None else None}
             for k, v in financial_summary(entrada, saida).items()]
    for chave, caminho, dinheiro in FATOS_EXTRATO:
        bruto = _pegar(perfil, caminho)
        valor = _dinheiro(bruto) if dinheiro else (None if bruto is None else str(bruto))
        if valor is not None:
            fatos.append({'id': chave, 'value': valor, 'origin': ORIGEM, 'period': periodo})
    return fatos, periodo


def _perfil_padrao(codigo):
    from apps.context_agent_datadriven.services import usuario_real
    return usuario_real.perfil(codigo)


def dados_do_titular(titular, fonte=None):
    """-> (fatos, dados_usuario). Toda falha vira estado declarado, sem número."""
    if not titular:
        return [], {'estado': 'SEM_TITULAR', 'selo': None}
    from apps.context_agent_datadriven.services import usuario_real
    try:
        perfil = (fonte or _perfil_padrao)(titular['codigo'])
        fatos, periodo = fatos_do_titular(perfil)
    except usuario_real.UsuarioRealDesligado:
        return [], {'estado': 'OFF', 'selo': None, 'motivo': 'USUARIO_REAL_ATIVO=0'}
    except Exception as erro:  # BigQuery sem ADC/rede, UUID fora da base, perfil incompleto
        return [], {'estado': 'NAO_MEDIDO', 'selo': None, 'motivo': type(erro).__name__}
    usuario = perfil.get('usuario') or {}
    return fatos, {'estado': 'MEDIDO', 'selo': perfil.get('selo'), 'data_corte': perfil.get('data_corte'),
                   'janela': periodo, 'indice_base': usuario.get('indice')}


def build_context(*, reference_date=None, titular=None, fonte=None):
    today = reference_date or datetime.now(timezone.utc).date()
    sources = []
    index = json.loads((KNOWLEDGE / 'indice.json').read_text(encoding='utf-8'))
    for record in index['documentos']:
        raw = (KNOWLEDGE / record['arquivo']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != record['sha256']:
            raise ValueError('Evidence integrity mismatch')
        doc = json.loads(raw)
        start = date.fromisoformat(record['inicio_vigencia_declarado'])
        for article in doc['artigos']:
            status = 'future' if today < start else 'current_according_to_research'
            if today >= date(2027, 7, 1):
                status = 'historical_requires_revalidation' if doc['id'] == 'RC-08-2023' else 'requires_revalidation'
            if today < date.fromisoformat(doc['identificacao']['data_ato']):
                continue
            sources.append({'id': article['id'], 'text': article['texto'], 'status': status,
                            'valid_from': start.isoformat(), 'url': doc['proveniencia']['url_registro_oficial'],
                            'limitations': doc['proveniencia']['limitacoes']})
    sources.extend(json.loads((KNOWLEDGE / 'institutional.json').read_text(encoding='utf-8'))['sources'])
    facts, dados_usuario = dados_do_titular(titular, fonte)
    medido = dados_usuario['estado'] == 'MEDIDO'
    missing = ['saldo', 'atraso', 'renda_recorrente', 'catalogo_de_produtos']
    if not medido:
        missing.insert(0, 'dados_financeiros_do_titular')
    limitations = ['Base parcial; não certifica conformidade nem autenticidade legal.',
                   'PENDENTE não comprova fato institucional. Revalidar versões antes de uso material.']
    if medido:
        limitations.append('Números do titular: médias mensais do extrato da base sintética do hackathon (BigQuery), '
                           'não de conta bancária real. Entrada não é renda recorrente; fluxo negativo não é atraso.')
    else:
        limitations.append(f"Dados financeiros do titular {dados_usuario['estado']} nesta resposta: "
                           'nenhum número do titular foi consultado; não são zero.')
    context = {'schema_version': '1.0', 'as_of': datetime.now(timezone.utc).isoformat(),
               'reference_date': today.isoformat(),
               'financial_period': dados_usuario.get('data_corte') if medido else None,
               'currency': 'BRL', 'snapshot_version': (dados_usuario.get('selo') or {}).get('medido_em') if medido else None,
               'facts': facts, 'sources': sources, 'dados_usuario': dados_usuario,
               'missing_data': missing, 'limitations': limitations}
    if titular:
        context['titular'] = {'pessoa': titular['pessoa'], 'codigo': titular['codigo']}  # sem gênero (dono 10:22)
    return context
