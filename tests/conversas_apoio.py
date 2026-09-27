"""Dublês dos testes de apps/conversas (portados de agente-app-mobile/agent_backend/tests, commit 1302ba5).

Nada aqui chama rede: FakeGateway é um dublê explícito, nunca evidência de chamada ao Gemini, e o perfil
financeiro é um dicionário no formato de services/usuario_real.perfil.
"""
import asyncio
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'desafio_itau.settings')
import django  # noqa: E402

django.setup()

MARIA = '00108ccd-699c-453a-a9f9-a66aad6e03e5'
EDUARDO = '001221d1-3626-45c1-807a-990502adf808'
TITULAR = {'codigo': MARIA, 'pessoa': 'Maria', 'genero': 'F', 'indice': 1}
CSV = ('indice,id_usuario,nome,genero,movimentos,meses,primeiro_anomes,ultimo_anomes\n'
       f'1,{MARIA},Maria,F,433,12,202501,202512\n'
       f'2,{EDUARDO},Eduardo,M,750,12,202501,202512\n')
SELO = {'fonte': 'batalha-time-02-lxof.hackathon_dados.extrato_sintetico', 'natureza_da_base': 'sintetica',
        'autenticacao': 'ADC', 'medido_em': '2026-09-27T05:17:52-03:00', 'jobs': {'perfil_t3': 'job-teste'},
        'bytes_processados': 10, 'tempo_consulta_ms': 1.0, 'cache': False}
PERFIL = {
    'usuario': {'indice': 1, 'id_usuario': MARIA},
    'data_corte': '2025-12-22',
    'resumo': {'segmento_t3': 'Vulnerável', 'inflow_mensal': 8828.12, 'outflow_mensal': 10790.43,
               'surplus_mensal': -1962.31, 'taxa_surplus_pct': -22.23, 'meses_na_janela': 11},
    'visoes': {'perfil_t3': {'essencial_mensal': 3983.87, 'compromisso_mensal': 5006.58, 'discricionario_mensal': 1664.13},
               'recorrencias': {'assinaturas_mensal': 109.47},
               'dividas': {'pct_inflow_comprometido': 56.71, 'juros_pagos_total': 475.37},
               'discricionario': {'maior_categoria_discricionaria': 'Lojas e sites', 'maior_categoria_total': 11185.07}},
    'selo': SELO,
}


def fonte_falsa(codigo):
    assert codigo == MARIA
    return PERFIL


def fonte_quebrada(codigo):
    from apps.context_agent_datadriven.services.usuario_real import FonteIndisponivel
    raise FonteIndisponivel('sem ADC')


def contexto_com(fonte):
    from apps.conversas.context import build_context
    return lambda titular=None: build_context(titular=titular, fonte=fonte)


class FakeGateway:
    """Explicit test double; never evidence of a live Gemini call."""
    def __init__(self, reply='Um fluxo negativo não comprova atraso. Há algum pagamento vencido?'):
        self.calls = []
        self.reply = reply

    async def input_guard(self, message, history):
        self.calls.append(('input', message, history.copy()))
        return {'decision': 'allow', 'reason_codes': [], 'constraints': [], 'policy_version': '1.0'}

    async def generate(self, message, context, history, constraints, titular=None):
        self.calls.append(('generate', context, history.copy()))
        return {'reply': self.reply, 'status': 'ok', 'capabilities': ['orcamento'], 'claims': [], 'missing_data': ['atraso']}

    async def output_guard(self, message, draft, context):
        self.calls.append(('output', draft))
        return {'decision': 'release', 'reason_codes': [], 'constraints': [], 'policy_version': '1.0'}


def payload(text='Meu mês ficou negativo', mid='msg-001', cid=None):
    return {'schema_version': '1.0', 'conversation_id': cid, 'client_message_id': mid, 'message': text}


def run(coro):
    return asyncio.run(coro)
