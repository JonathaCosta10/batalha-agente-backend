"""Dados medidos de uma interação: situação do mês (SOBROU/FALTOU/EQUILIBRIO/NAO_MEDIDO), 50-30-20 e T3.

Uma consulta nova (SQL_MENSAL, sobre o mesmo prefixo `_base_cliente.sql` das visões i.agora) devolve, por
mês da janela, entradas, saídas e as saídas separadas em necessidades / desejos / futuro / fora da regra
pela SUBCATEGORIA real (`nom_cate_micro`) — as 92 subcategorias de saída medidas em 2026-09-27 no
`extrato_sintetico` estão em CLASSE_50_30_20. Subcategoria nova na base cai em `saidas_sem_classe`
(o guard da resposta exige 0, como `saidas_sem_grupo` do T3).

Situação: sinal de (entradas − saídas) do MÊS DE REFERÊNCIA = último mês completo antes da data de corte
(corte 2025-12-22 -> novembro/2025). |saldo| < 1 % das entradas do mês = EQUILIBRIO. Mês sem movimento
ou fonte fora = NAO_MEDIDO, nunca zero. A média da janela (T3) vai junto, com a sua própria situação.

50-30-20 (referência de orçamento, NÃO norma do BCB): base = média mensal das entradas da janela.
necessidades = saídas classe necessidades; desejos = classe desejos; futuro = sobra positiva + classe
futuro (consórcio, título de capitalização). `fora_da_regra` (fatura de cartão, transferências, saque,
boleto genérico) não é classificável sem o detalhe da fatura: é mostrado à parte, nunca somado a uma classe.
"""
import time
from datetime import date
from decimal import Decimal

from desafio_itau import politica

NECESSIDADES, DESEJOS, FUTURO, FORA = 'necessidades', 'desejos', 'futuro', 'fora_da_regra'
# Valores da política versionada (desafio_itau/politica/operacional-v1.json); equivalência provada em
# tests/test_politica_operacional.py. Os nomes ficam para os consumidores existentes.
REFERENCIA_50_30_20 = {c: int(politica.parametro('orcamento.referencia_50_30_20', c))
                       for c in (NECESSIDADES, DESEJOS, FUTURO)}
LIMIAR_EQUILIBRIO_PCT = float(politica.parametro('situacao.equilibrio', 'limiar_pct'))
SOBROU, FALTOU, EQUILIBRIO, NAO_MEDIDO = 'SOBROU', 'FALTOU', 'EQUILIBRIO', 'NAO_MEDIDO'
MESES_PT = ('janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro',
            'outubro', 'novembro', 'dezembro')

_N, _D, _F, _X = NECESSIDADES, DESEJOS, FUTURO, FORA
# (macro, subcategoria) -> classe. Subcategorias medidas: SELECT DISTINCT nom_cate_macro, nom_cate_micro
# WHERE tipo='S' (job f2d70b4d-31d5-4232-be95-096c675df196, 2026-09-27, 19,6 MB).
CLASSE_50_30_20 = {
    **{('Casa', m): _N for m in ('Agua e esgoto', 'Celular', 'Condominio', 'Energia eletrica', 'Gas', 'IPTU',
                                'Outras contas', 'Outras despesas de moradia', 'Pagamento de aluguel',
                                'Seguro residencial', 'TV Internet celular e telefone')},
    **{('Casa', m): _D for m in ('Empregados domesticos', 'Jardinagem', 'Lavanderia')},
    **{('Mercado', m): _N for m in ('Casa de Carnes', 'Feira livre', 'Mercado', 'Outros mercados')},
    **{('Educacao', m): _N for m in ('Entidades de classe', 'Mensalidade escolar', 'Outras despesas de educacao')},
    ('Educacao', 'Curso de idiomas'): _D,
    **{('Transporte publico', m): _N for m in ('Passagem de onibus', 'Transporte publico')},
    ('Posto de combustivel', 'Posto de combustivel'): _N,
    ('Posto de combustivel', 'Loja de conveniencia'): _D,
    **{('Veiculos', m): _N for m in ('Estacionamento', 'Licenciamento IPVA e DPVAT', 'Manutencao e reparo', 'Multa',
                                    'Outros gastos com transporte', 'Pedagio', 'Seguro de automovel')},
    ('Veiculos', 'Aluguel de carro'): _D,
    **{('Emprestimos e financiamentos', m): _N for m in ('Emprestimos', 'Financiamento de imovel', 'Outros emprestimos')},
    **{('Produtos financeiros', m): _N for m in ('Anuidade e pacote de servico', 'Juros pagos',
                                                'Outras tarifas financeiras', 'Outros seguros', 'Seguros')},
    **{('Produtos financeiros', m): _F for m in ('Consorcio', 'Titulo de capitalizacao')},
    ('Produtos financeiros', 'Pagamento de fatura'): _X,
    ('Boletos diversos', 'Boleto'): _X,
    **{('Lazer', m): _D for m in ('Associacoes e clubes', 'Cinema', 'Eletronicos', 'Eventos e festas',
                                 'Ingresso de shows', 'Livros musica e video', 'Museu e teatro',
                                 'Outros entretenimentos', 'Videogames')},
    **{('Lojas e sites', m): _D for m in ('Artigos esportivos', 'Brinquedos e artigos infantis', 'Compras',
                                         'Moveis e decoracao', 'Vestuario e acessorios')},
    ('Lojas e sites', 'Manutencao da casa'): _N,
    **{('Viagens', m): _D for m in ('Compra de moedas', 'Hospedagem', 'Outros gastos de viagem', 'Passagem aerea e taxas')},
    **{('Restaurantes', m): _D for m in ('Cafeteria', 'Outras comidas e bebidas', 'Padaria', 'Restaurantes')},
    ('Delivery', 'Delivery'): _D,
    ('Assinaturas', 'Assinaturas'): _D,
    **{('Cuidados pessoais', m): _D for m in ('Outros cuidados pessoais', 'Outros esportes', 'Produtos de beleza',
                                             'Salao de beleza ou barbearia')},
    ('Transporte por app', 'Transporte por app'): _D,
    **{('Pets', m): _D for m in ('Outros gastos de animais', 'Pet shop')},
    ('Pets', 'Veterinario'): _N,
    **{('Outros gastos', m): _N for m in ('Contabilidade', 'Multa por atraso', 'Outras despesas com impostos',
                                         'Pagamento de impostos', 'Pensao alimenticia')},
    **{('Outros gastos', m): _X for m in ('Cheque', 'Diversos', 'Frete e correios', 'Outros gastos',
                                         'Outros servicos', 'Publicidade')},
    ('Saque', 'Saque'): _X,
    ('Transferencias diversas', 'Outras transferencias'): _X,
}

SQL_MENSAL = """
, classes AS (
  {{CLASSES}}
),
mensal AS (
  SELECT
    m.anomes,
    SUM(IF(m.tipo = 'E', m.valor, 0)) AS entradas,
    SUM(IF(m.tipo = 'S', m.valor, 0)) AS saidas,
    SUM(IF(m.tipo = 'S' AND c.classe = 'necessidades', m.valor, 0)) AS necessidades,
    SUM(IF(m.tipo = 'S' AND c.classe = 'desejos', m.valor, 0)) AS desejos,
    SUM(IF(m.tipo = 'S' AND c.classe = 'futuro', m.valor, 0)) AS futuro_programado,
    SUM(IF(m.tipo = 'S' AND c.classe = 'fora_da_regra', m.valor, 0)) AS fora_da_regra,
    COUNTIF(m.tipo = 'S' AND c.classe IS NULL) AS saidas_sem_classe,
    SUM(IF(m.tipo = 'S' AND m.macro = 'Emprestimos e financiamentos', m.valor, 0)) AS emprestimos,
    SUM(IF(m.tipo = 'S' AND m.micro = 'Juros pagos', m.valor, 0)) AS juros_pagos,
    COUNTIF(m.tipo = 'S' AND m.micro = 'Multa por atraso') AS multas_atraso
  FROM mov AS m
  LEFT JOIN classes AS c
    ON c.macro = m.macro AND c.micro = m.micro AND m.tipo = 'S'
  GROUP BY m.anomes
)
SELECT
  anomes,
  ROUND(entradas, 2) AS entradas,
  ROUND(saidas, 2) AS saidas,
  ROUND(necessidades, 2) AS necessidades,
  ROUND(desejos, 2) AS desejos,
  ROUND(futuro_programado, 2) AS futuro_programado,
  ROUND(fora_da_regra, 2) AS fora_da_regra,
  saidas_sem_classe,
  ROUND(emprestimos, 2) AS emprestimos,
  ROUND(juros_pagos, 2) AS juros_pagos,
  multas_atraso
FROM mensal
ORDER BY anomes
"""


def _texto_sql(valor):
    if "'" in valor or '\\' in valor:
        raise ValueError(f'Caractere proibido no SQL: {valor!r}.')
    return f"'{valor}'"


def cte_classes(mapa=None):
    mapa = CLASSE_50_30_20 if mapa is None else mapa
    linhas = [f'SELECT {_texto_sql(ma)} AS macro, {_texto_sql(mi)} AS micro, {_texto_sql(c)} AS classe'
              for (ma, mi), c in sorted(mapa.items())]
    return '\n  UNION ALL '.join(linhas)


def montar_sql():
    from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora import t3, visoes
    base = (visoes.PASTA_SQL / '_base_cliente.sql').read_text(encoding='utf-8')
    return t3.renderizar_sql(base + SQL_MENSAL.replace('{{CLASSES}}', cte_classes()))


def consultar_mensal(codigo, data_corte=None):
    """-> (linhas por mês, selo). BigQuery via o mesmo executor/selo de usuario_real."""
    from apps.context_agent_datadriven.services import usuario_real
    corte = usuario_real.validar_data_corte(data_corte)
    executor = usuario_real._novo_executor()
    inicio = time.perf_counter()
    try:
        linhas = executor.executar(montar_sql(), {'id_usuario': codigo, 'data_corte': corte})
    except Exception as erro:
        raise usuario_real.FonteIndisponivel(f'mensal_50_30_20: {type(erro).__name__}: {erro}') from erro
    job = getattr(executor, 'ultimo_job', {}) or {}
    selo = usuario_real._selo({'mensal_50_30_20': job.get('job_id')}, job.get('bytes_processados', 0),
                              (time.perf_counter() - inicio) * 1000)
    return [{k: (float(v) if isinstance(v, Decimal) else v) for k, v in l.items()} for l in linhas], {**selo, 'data_corte': corte.isoformat()}


# ---------------------------------------------------------------- regras puras (testáveis sem BigQuery)

def mes_referencia(data_corte):
    """Último mês completo antes do mês da data de corte: 2025-12-22 -> 202511."""
    corte = date.fromisoformat(str(data_corte)[:10])
    ano, mes = (corte.year, corte.month - 1) if corte.month > 1 else (corte.year - 1, 12)
    return ano * 100 + mes


def nome_mes(anomes):
    return f'{MESES_PT[anomes % 100 - 1]} de {anomes // 100}'


def situacao_de(entradas, saidas, limiar_pct=LIMIAR_EQUILIBRIO_PCT):
    """Sinal de entradas − saídas. Falta de dado: NAO_MEDIDO (nunca zero)."""
    if entradas is None or saidas is None:
        return NAO_MEDIDO
    saldo = round(float(entradas) - float(saidas), 2)
    if entradas > 0 and abs(saldo) < entradas * limiar_pct / 100:
        return EQUILIBRIO
    if saldo > 0:
        return SOBROU
    if saldo < 0:
        return FALTOU
    return EQUILIBRIO if entradas > 0 else NAO_MEDIDO


def _pct(parte, total):
    return round(parte / total * 100, 1) if total else None


def meses_faltantes(anomes):
    """AAAAMM ausentes entre o primeiro e o último mês presentes. Lacuna nas pontas da janela não é detectável
    aqui (a janela esperada vem do SQL); isso fica registrado como limitação."""
    if not anomes:
        return []
    presentes, (a, m), fim, saida = set(anomes), divmod(min(anomes), 100), max(anomes), []
    while a * 100 + m <= fim:
        if a * 100 + m not in presentes:
            saida.append(a * 100 + m)
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return saida


def resumir_mensal(linhas, data_corte):
    """Linhas por mês -> {mes_referencia, media, regra_50_30_20, projecao}. Tudo derivado das linhas."""
    ref = mes_referencia(data_corte)
    por_mes = {int(l['anomes']): l for l in linhas}
    atual = por_mes.get(ref)
    mes = {'anomes': ref, 'nome': nome_mes(ref), 'entradas': None, 'saidas': None, 'saldo': None,
           'situacao': NAO_MEDIDO}
    if atual:
        mes.update(entradas=atual['entradas'], saidas=atual['saidas'],
                   saldo=round(atual['entradas'] - atual['saidas'], 2),
                   situacao=situacao_de(atual['entradas'], atual['saidas']))
    mes['papel'] = 'informativo: o mês mais recente não decide a situação da conversa (regra do dono, 06:22)'
    n = len(linhas)
    if not n:
        return {'mes_referencia': mes, 'media': None, 'regra_50_30_20': None, 'projecao': None,
                'saidas_sem_classe': None, 'situacao_conversa': situacao_conversa(None, data_corte)}
    soma = lambda k: sum(float(l[k] or 0) for l in linhas)  # noqa: E731
    media = {k: round(soma(k) / n, 2) for k in ('entradas', 'saidas', 'necessidades', 'desejos',
                                                 'futuro_programado', 'fora_da_regra')}
    media['saldo'] = round(media['entradas'] - media['saidas'], 2)
    media['meses'] = n
    media['janela'] = f'{nome_mes(int(linhas[0]["anomes"]))} a {nome_mes(int(linhas[-1]["anomes"]))}'
    media['anomes'] = [int(l['anomes']) for l in linhas]  # meses citáveis (guard alucinacao.datas)
    # Lacuna: mês sem linha dentro da janela sai do denominador e infla a média. Não se sabe se foi mês sem
    # movimento ou dado ausente, então NÃO se imputa zero: expõe-se a lacuna (entrega parcial, 2026-09-27).
    faltantes = meses_faltantes(media['anomes'])
    media['meses_faltantes'] = faltantes
    media['cobertura'] = 'LACUNA' if faltantes else 'COMPLETA'
    media['situacao'] = situacao_de(media['entradas'], media['saidas'])
    renda = media['entradas']
    futuro_valor = round(max(media['saldo'], 0) + media['futuro_programado'], 2)
    classes = {
        NECESSIDADES: {'valor': media['necessidades'], 'pct': _pct(media['necessidades'], renda)},
        DESEJOS: {'valor': media['desejos'], 'pct': _pct(media['desejos'], renda)},
        FUTURO: {'valor': futuro_valor, 'pct': _pct(futuro_valor, renda)},
        FORA: {'valor': media['fora_da_regra'], 'pct': _pct(media['fora_da_regra'], renda)},
    }
    from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora.consultas import diagnostico_50_30_20
    diagnostico = (diagnostico_50_30_20(classes[NECESSIDADES]['pct'], classes[DESEJOS]['pct'], classes[FUTURO]['pct'])
                   if renda else None)
    regra = {'base': f'média mensal das entradas, {media["janela"]}', 'renda_base': renda,
             'referencia_pct': REFERENCIA_50_30_20, **classes, 'diagnostico_estudo_c06': diagnostico,
             'classificacao': 'por subcategoria real (nom_cate_micro), CLASSE_50_30_20'}
    return {'mes_referencia': mes, 'media': media, 'regra_50_30_20': regra,
            'projecao': projetar(media), 'saidas_sem_classe': int(sum(int(l['saidas_sem_classe'] or 0) for l in linhas)),
            'divida': resumir_divida(linhas, renda), 'situacao_conversa': situacao_conversa(media, data_corte)}


# Regra do dono (2026-09-27 06:22): "negativado = saldo completo negativo = média dos meses completos". A situação da
# CONVERSA é o sinal do saldo MÉDIO mensal da janela de meses completos (corte 2025-12-22 -> jan-nov/2025), com o mesmo
# limiar de EQUILIBRIO (|saldo| < 1 % das entradas). É a mesma base de `negativado_na_media` de usuario-real/<ref>/saldo-mes/.
# O mês mais recente (`mes_referencia`) fica só como informação secundária. Conflito medido pelo front às 06:53 (8001).
def situacao_conversa(media, data_corte):
    corte = date.fromisoformat(str(data_corte)[:10])
    registros_ate = corte.strftime('%d/%m/%Y')
    if not media:
        return {'situacao': NAO_MEDIDO, 'base': 'media_meses_completos', 'janela': None, 'registros_ate': registros_ate,
                'saldo_medio': None, 'entradas_media': None, 'saidas_media': None}
    return {'situacao': media['situacao'], 'base': 'media_meses_completos', 'janela': media['janela'],
            'registros_ate': registros_ate, 'saldo_medio': media['saldo'], 'entradas_media': media['entradas'],
            'saidas_media': media['saidas'], 'limiar_equilibrio_pct': LIMIAR_EQUILIBRIO_PCT,
            'cobertura': media.get('cobertura'), 'meses_faltantes': media.get('meses_faltantes', []),
            'regra': 'dono 2026-09-27 06:22: negativado = média dos meses completos'}


def situacao_da_conversa(dados):
    """A situação que decide fluxo, texto e guards. Sem média medida: NAO_MEDIDO (nunca o mês isolado)."""
    return ((dados or {}).get('situacao_conversa') or {}).get('situacao', NAO_MEDIDO)


# Dívida "relevante" (gatilho do cenário de consolidação; desenho §Cenários). Na base sintética 100 % dos 1000
# usuários têm algum empréstimo, juros ou multa (job 91e4cb80-21ea-4240-a15c-1d47cb24beb4, 2026-09-27): "ter dívida"
# sozinho não discrimina. Relevante = empréstimos + juros pagos >= 10 % da entrada média, ou pelo menos uma multa por
# atraso (sinal de inadimplemento, RC 8/2023 art. 2 §1º III).
LIMIAR_DIVIDA_PCT_ENTRADAS = float(politica.parametro('divida.relevante', 'limiar_pct_entradas'))


def resumir_divida(linhas, renda_media):
    """Médias mensais de dívida na janela. Valor nulo numa linha não vira zero: o resumo fica NAO_MEDIDO.

    A decisão `relevante` é tomada sobre o percentual EXATO (Decimal) pela regra `divida.relevante`; o
    `pct_da_entrada_media` exibido é arredondado a 1 casa só depois (9,96 % não vira 10,0 % para decidir)."""
    colunas = ('emprestimos', 'juros_pagos', 'multas_atraso')
    if not linhas or any(k not in linhas[0] for k in colunas):
        return {'estado': NAO_MEDIDO, 'motivo': 'consulta sem colunas de dívida'}
    if any(l.get(k) is None for l in linhas for k in colunas):
        return {'estado': NAO_MEDIDO, 'motivo': 'valor nulo na janela (não é tratado como zero)'}
    n = len(linhas)
    emp_exato = sum(Decimal(str(l['emprestimos'])) for l in linhas) / n
    jur_exato = sum(Decimal(str(l['juros_pagos'])) for l in linhas) / n
    multas = int(sum(int(l['multas_atraso']) for l in linhas))
    renda = None if renda_media is None else Decimal(str(renda_media))
    pct_exato = (emp_exato + jur_exato) / renda * 100 if renda else None
    decisao = politica.avaliar('divida.relevante', {'divida_pct_entrada_media': pct_exato,
                                                    'multas_por_atraso_na_janela': multas})
    emp, jur = round(float(emp_exato), 2), round(float(jur_exato), 2)
    return {'estado': 'MEDIDO', 'emprestimos_mensal_medio': emp, 'juros_pagos_mensal_medio': jur,
            'divida_mensal_medio': round(emp + jur, 2),
            'multas_por_atraso_na_janela': multas,
            'pct_da_entrada_media': None if pct_exato is None else round(float(pct_exato), 1),
            'limiar_pct': LIMIAR_DIVIDA_PCT_ENTRADAS, 'relevante': decisao is True,
            'regra': politica.referencia('divida.relevante')}


# ---------------------------------------------------------------- inclinação de gasto por subcategoria real

SQL_SUBCATEGORIAS = """
SELECT anomes, macro, micro, ROUND(SUM(valor), 2) AS valor
FROM mov
WHERE tipo = 'S'
GROUP BY anomes, macro, micro
ORDER BY anomes, macro, micro
"""
# Limiar documentado de "leve inclinação": média dos 3 últimos meses vs média mensal da janela inteira; variação
# >= 15 % (o mesmo 15 % do limiar T3) E diferença >= R$ 30/mês, só em subcategorias de DESEJOS ou Mercado (gasto que
# depende de escolha) com média >= R$ 50/mês. "Leve" é o tom da frase, não a magnitude.
INCLINACAO = {'meses_recentes': int(politica.parametro('gasto.inclinacao', 'meses_recentes')),
              **{k: float(politica.parametro('gasto.inclinacao', k))
                 for k in ('variacao_min_pct', 'diferenca_min_reais', 'media_min_reais')}}


def consultar_subcategorias(codigo, data_corte=None):
    """-> (linhas anomes/macro/micro/valor de saídas, selo). Mesmo executor/selo de usuario_real."""
    from apps.context_agent_datadriven.pastas_raiz.estudos.i_agora import t3, visoes
    from apps.context_agent_datadriven.services import usuario_real
    corte = usuario_real.validar_data_corte(data_corte)
    base = (visoes.PASTA_SQL / '_base_cliente.sql').read_text(encoding='utf-8')
    executor = usuario_real._novo_executor()
    inicio = time.perf_counter()
    try:
        linhas = executor.executar(t3.renderizar_sql(base + SQL_SUBCATEGORIAS), {'id_usuario': codigo, 'data_corte': corte})
    except Exception as erro:
        raise usuario_real.FonteIndisponivel(f'subcategorias: {type(erro).__name__}: {erro}') from erro
    job = getattr(executor, 'ultimo_job', {}) or {}
    selo = usuario_real._selo({'subcategorias_mensal': job.get('job_id')}, job.get('bytes_processados', 0),
                              (time.perf_counter() - inicio) * 1000)
    return ([{k: (float(v) if isinstance(v, Decimal) else v) for k, v in l.items()} for l in linhas],
            {**selo, 'data_corte': corte.isoformat()})


def inclinacao(linhas, limiares=INCLINACAO):
    """-> {alta, queda, maior_desejo_recente} com X, valores e janela; sem sinal: None. Sem linhas: NAO_MEDIDO."""
    if not linhas:
        return {'estado': NAO_MEDIDO, 'motivo': 'sem linhas de subcategoria'}
    meses = sorted({int(l['anomes']) for l in linhas})
    n, k = len(meses), limiares['meses_recentes']
    if n <= k:
        return {'estado': NAO_MEDIDO, 'motivo': f'janela de {n} meses não comporta {k} recentes'}
    recentes = meses[-k:]
    soma, soma_rec = {}, {}
    for l in linhas:
        if CLASSE_50_30_20.get((l['macro'], l['micro'])) != DESEJOS and l['macro'] != 'Mercado':
            continue
        chave = l['micro'] or l['macro']
        soma[chave] = soma.get(chave, 0.0) + float(l['valor'] or 0)
        if int(l['anomes']) in recentes:
            soma_rec[chave] = soma_rec.get(chave, 0.0) + float(l['valor'] or 0)
    cands = []
    for x, total in soma.items():
        media, rec = round(total / n, 2), round(soma_rec.get(x, 0.0) / k, 2)
        if media < limiares['media_min_reais']:
            continue
        dif, var = round(rec - media, 2), round((rec / media - 1) * 100, 1)
        cands.append({'subcategoria': x, 'media_janela': media, 'media_recente': rec, 'diferenca': dif,
                      'variacao_pct': var})

    def sinal(c):
        return abs(c['variacao_pct']) >= limiares['variacao_min_pct'] and abs(c['diferenca']) >= limiares['diferenca_min_reais']

    altas = sorted((c for c in cands if c['diferenca'] > 0 and sinal(c)), key=lambda c: (-c['diferenca'], c['subcategoria']))
    quedas = sorted((c for c in cands if c['diferenca'] < 0 and sinal(c)), key=lambda c: (c['diferenca'], c['subcategoria']))
    maior = sorted(cands, key=lambda c: (-c['media_recente'], c['subcategoria']))
    return {'estado': 'MEDIDO', 'janela': f'{nome_mes(meses[0])} a {nome_mes(meses[-1])}',
            'recentes': f'{nome_mes(recentes[0])} a {nome_mes(recentes[-1])}', 'limiares': dict(limiares),
            'alta': altas[0] if altas else None, 'queda': quedas[0] if quedas else None,
            'maior_desejo_recente': maior[0] if maior else None}


def projetar(media):
    """Quanto tempo até o futuro chegar a 20 %, cortando só desejos. Taxas 5 %/8 % ao mês são HIPÓTESES."""
    from .projection import project
    renda = media['entradas']
    if not renda:
        return {'status': NAO_MEDIDO}
    teto_saidas = 1 - REFERENCIA_50_30_20[FUTURO] / 100  # 0,8 da renda: o futuro de referência (20 %) fica livre
    lacuna = round(max(0.0, media['saidas'] - media['futuro_programado'] - teto_saidas * renda), 2)
    base = {'lacuna_mensal_para_20': lacuna, 'hipotese': 'reduzir desejos 5 % ou 8 % ao mês (G(n)=G·(1−r)^n)',
            'natureza': 'projeção hipotética, não medição'}
    if lacuna == 0:
        return {**base, 'status': 'ja_no_cenario', 'meses_5': 0, 'meses_8': 0}
    if lacuna > media['desejos']:
        return {**base, 'status': 'desejos_nao_bastam', 'meses_5': None, 'meses_8': None,
                'desejos_mensal': media['desejos']}
    alvo = round(media['desejos'] - lacuna, 2)
    r = project(f"{media['desejos']:.2f}", f'{alvo:.2f}')
    return {**base, 'status': r['status'], 'desejos_mensal': media['desejos'], 'desejos_alvo': alvo,
            'meses_5': r.get('n_5'), 'meses_8': r.get('n_8')}
