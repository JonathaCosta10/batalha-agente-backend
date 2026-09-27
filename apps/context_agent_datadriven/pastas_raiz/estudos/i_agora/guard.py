"""
Guard de inclusão do dado: o agente envia (dados + texto) e ESPERA a comparação.

O guard reexecuta o SELECT da própria visão (visoes.consultar_visao) com os mesmos
parâmetros, normaliza os dois lados e confere:

    dados      cada campo enviado existe na linha da query e bate após normalizar
    numeros    todo R$ e % escrito no texto tem fonte numa linha consultada,
               na precisão em que foi escrito (R$ 1.638 aceita 1638,49)
    segmento   o segmento declarado é o segmento_t3 que o SQL calculou
    tom        exclamações, termos proibidos e exigidos do perfil do segmento
    sentimento escore LÉXICO (-1..1) dentro da faixa do segmento; é contagem de
               palavras, não leitura semântica — sem palavra do léxico: NAO_MEDIDO

Veredito: qualquer REPROVADO reprova; senão, qualquer NAO_MEDIDO deixa NAO_MEDIDO;
senão APROVADO. Contrato: docs/estudo-i-agora/schemas/veredito-guard.schema.json.
"""

import re
from datetime import date, datetime, timedelta, timezone

from . import t3, visoes

APROVADO, REPROVADO, NAO_MEDIDO = "APROVADO", "REPROVADO", "NAO_MEDIDO"
BRT = timezone(timedelta(hours=-3))

LEXICO_POSITIVO = (
    "bom", "boa", "otimo", "otima", "excelente", "parabens", "consegue", "conseguir", "tranquilo",
    "tranquila", "positivo", "saudavel", "folga", "sobra", "crescer", "oportunidade", "equilibrio",
    "progresso", "conquista", "possivel", "seguranca", "incrivel", "fantastico", "maravilhoso",
    "sensacional", "perfeito",
)
LEXICO_NEGATIVO = (
    "problema", "dificil", "dificuldade", "preocupante", "risco", "perigo", "negativo", "negativa",
    "aperto", "falta", "ruim", "grave", "alerta", "atraso", "critico", "critica", "deficit",
    "prejuizo", "pesado", "pesada",
)

_NUMERO_BR = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?"
_ESCALA = r"(?:\s*(mil|milh(?:ão|ões)|bilh(?:ão|ões))\b)?"
_ESCALAS = {"mil": 1e3, "milhão": 1e6, "milhões": 1e6, "bilhão": 1e9, "bilhões": 1e9}
# "R$ 1,6 mil" e "1.638,49 reais" são valores; antes de 2026-09-27 só "R$ <n>" era lido (revisão Gemini 04:38).
_RE_REAIS = re.compile(r"R\$\s*(" + _NUMERO_BR + ")" + _ESCALA
                       + r"|(" + _NUMERO_BR + ")" + _ESCALA + r"\s*reais\b", re.IGNORECASE)
_RE_PCT = re.compile(r"(" + _NUMERO_BR + r")\s*(?:%|por\s*cento\b)", re.IGNORECASE)


def _checagem(nome, resultado, detalhe):
    return {"nome": nome, "resultado": resultado, "detalhe": detalhe}


def ler_numero_br(texto: str) -> tuple[float, int]:
    """'1.638,49' -> (1638.49, 2 casas). As casas definem a tolerância da comparação."""
    inteiro, _, decimais = texto.replace(".", "").partition(",")
    return float(f"{inteiro}.{decimais or 0}"), len(decimais)


def normalizar(valor):
    """Número -> float com 2 casas; texto monetário/percentual -> float; rótulo -> casefold sem acento."""
    if valor is None or isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return round(float(valor), 2)
    texto = str(valor).strip()
    casou = re.fullmatch(r"(?:R\$\s*)?(" + _NUMERO_BR + r")\s*%?", texto)
    if casou:
        return round(ler_numero_br(casou.group(1))[0], 2)
    return visoes.normalizar_texto(texto)


def comparar_dados(dados: dict, linha: dict) -> list[dict]:
    if not dados:
        return [_checagem("dados", REPROVADO, "envio sem dados: nada a comparar com a query")]
    saida = []
    for campo, enviado in dados.items():
        if campo not in linha:
            saida.append(_checagem(f"dados.{campo}", REPROVADO, "campo sem fonte na linha da visão"))
            continue
        a, b = normalizar(enviado), normalizar(linha[campo])
        igual = abs(a - b) <= 0.005 if isinstance(a, float) and isinstance(b, float) else a == b
        saida.append(_checagem(f"dados.{campo}", APROVADO if igual else REPROVADO,
                               f"enviado={enviado!r} query={linha[campo]!r}"))
    return saida


def numeros_do_texto(texto: str) -> list[dict]:
    """Cada número citado: valor já multiplicado pela escala; `tolerancia` é meia unidade da última casa escrita."""
    achados = []
    for m in _RE_REAIS.finditer(texto):
        numero, escala = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        valor, casas = ler_numero_br(numero)
        fator = _ESCALAS[escala.lower()] if escala else 1.0
        achados.append({"bruto": m.group(0), "tipo": "reais", "valor": valor * fator, "casas": casas,
                        "tolerancia": 0.5 * 10 ** -casas * fator})
    for m in _RE_PCT.finditer(texto):
        valor, casas = ler_numero_br(m.group(1))
        achados.append({"bruto": m.group(0), "tipo": "pct", "valor": valor, "casas": casas,
                        "tolerancia": 0.5 * 10 ** -casas})
    return achados


def conferir_numeros(texto: str, linhas: list[dict]) -> list[dict]:
    fontes = [float(v) for linha in linhas for v in linha.values()
              if isinstance(v, (int, float)) and not isinstance(v, bool)]
    saida = []
    for n in numeros_do_texto(texto):
        tolerancia = n["tolerancia"] + 1e-9
        fonte = next((f for f in fontes if abs(f - n["valor"]) <= tolerancia), None)
        saida.append(_checagem(f"numero {n['bruto']}", APROVADO if fonte is not None else REPROVADO,
                               f"fonte={fonte}" if fonte is not None else "número no texto sem fonte na query"))
    return saida


def escore_sentimento(texto: str) -> float | None:
    palavras = re.findall(r"[a-z]+", visoes.normalizar_texto(texto))
    pos = sum(p in LEXICO_POSITIVO for p in palavras)
    neg = sum(p in LEXICO_NEGATIVO for p in palavras)
    return None if pos + neg == 0 else (pos - neg) / (pos + neg)


def verificar_tom(texto: str, segmento: str) -> list[dict]:
    perfil = t3.PERFIS_DE_RESPOSTA[segmento]
    norm = visoes.normalizar_texto(texto)
    saida = []
    exclamacoes = texto.count("!")
    saida.append(_checagem("tom.exclamacoes", APROVADO if exclamacoes <= perfil["exclamacoes_max"] else REPROVADO,
                           f"{exclamacoes} (máx {perfil['exclamacoes_max']})"))
    achados = [p for p in perfil["proibidos"] if visoes.normalizar_texto(p) in norm]
    saida.append(_checagem("tom.proibidos", REPROVADO if achados else APROVADO, f"encontrados={achados}"))
    exigidos = [p for p in perfil["exigidos_um_de"] if visoes.normalizar_texto(p) in norm]
    saida.append(_checagem("tom.exigidos", APROVADO if exigidos else REPROVADO,
                           f"encontrados={exigidos} (precisa de um de {list(perfil['exigidos_um_de'])})"))
    escore = escore_sentimento(texto)
    minimo, maximo = perfil["sentimento"]
    if escore is None:
        saida.append(_checagem("sentimento", NAO_MEDIDO, "nenhuma palavra do léxico: escore não medido"))
    else:
        dentro = minimo <= escore <= maximo
        saida.append(_checagem("sentimento", APROVADO if dentro else REPROVADO,
                               f"escore léxico {escore:.2f}, faixa [{minimo}, {maximo}]"))
    return saida


def veredito(checagens: list[dict]) -> str:
    resultados = {c["resultado"] for c in checagens}
    if REPROVADO in resultados:
        return REPROVADO
    return NAO_MEDIDO if NAO_MEDIDO in resultados else APROVADO


def verificar_envio(envio: dict, executor=None) -> dict:
    """`envio`: id_usuario, data_corte, topico, categoria?, segmento_t3, dados, texto
    (docs/estudo-i-agora/schemas/envio-agente.schema.json)."""
    corte = envio.get("data_corte") or visoes.DATA_CORTE_TESE
    corte = date.fromisoformat(corte) if isinstance(corte, str) else corte
    visao = visoes.consultar_visao(envio["topico"], envio["id_usuario"], corte, envio.get("categoria"), executor)
    perfil = visao if envio["topico"] == "perfil_t3" else visoes.consultar_visao(
        "perfil_t3", envio["id_usuario"], corte, None, executor)
    segmento_query = perfil["linha"]["segmento_t3"]

    checagens = comparar_dados(envio.get("dados") or {}, visao["linha"])
    checagens += conferir_numeros(envio["texto"], [visao["linha"], perfil["linha"]])
    declarado = envio.get("segmento_t3")
    checagens.append(_checagem("segmento", APROVADO if declarado == segmento_query else REPROVADO,
                               f"declarado={declarado!r} query={segmento_query!r}"))
    sem_grupo = perfil["linha"].get("saidas_sem_grupo")
    checagens.append(_checagem("mapa_grupos", APROVADO if sem_grupo == 0 else REPROVADO,
                               f"saídas sem grupo no mapa T3: {sem_grupo}"))
    checagens += verificar_tom(envio["texto"], segmento_query)
    return {
        "veredito": veredito(checagens),
        "topico": visao["topico"],
        "parametros": visao["parametros"],
        "sql_sha256": visao["sql_sha256"],
        "segmento_t3": segmento_query,
        "linha_fonte": visao["linha"],
        "checagens": checagens,
        "verificado_em": datetime.now(BRT).strftime("%Y-%m-%dT%H:%M BRT"),
    }
