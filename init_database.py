#!/usr/bin/env python3
"""
Criação e população do banco de dados SQLite para o Desafio Itaú.

O esquema NÃO é criado aqui: as tabelas vêm das migrações Django
(`apps/*/migrations/`). Este script:
0. Corre `manage.py migrate` (cria/atualiza as tabelas e a django_migrations).
1. Grava o registro do fluxo de auditoria com:
   - "Que bom ter você aqui,[VARIAVEL_NOME] !"
   - TEXTO_1[NEUTRO]
   - TEXTO_2[MASCULINO]
   - TEXTO_3[FEMININO]
   - Botão "E agora?"
2. Grava a base dos 1.000 clientes com diferenciação determinística por ID (F e M).
3. Grava a matriz fixa de produtos (Template 3).
4. Cria a chave ON/OFF 'inteiração-tela-iai' ligada (ON) se ainda não existir;
   uma escolha já gravada é mantida.

Idempotente: pode correr de novo sobre o mesmo banco.
Uso (a partir desta pasta):  ..\\.venv\\Scripts\\python.exe init_database.py
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import transaction  # noqa: E402

from apps.recomendacao.models import (  # noqa: E402
    AuditoriaFluxoConfig,
    ClienteRegistro,
    FeatureFlagInteracaoTelaIAI,
    PlanilhaProdutoRegistro,
)

NOMES_F = ["Ana", "Beatriz", "Camila", "Daniela", "Eduarda", "Fernanda", "Gabriela", "Helena", "Isabela", "Juliana", "Larissa", "Mariana", "Natália", "Patrícia", "Rafaela", "Sofia", "Tatiane", "Vanessa", "Yasmin", "Carolina"]
NOMES_M = ["Alexandre", "Bruno", "Carlos", "Diego", "Eduardo", "Felipe", "Gabriel", "Henrique", "Igor", "João", "Lucas", "Mateus", "Nicolas", "Otávio", "Paulo", "Rafael", "Rodrigo", "Thiago", "Vinícius", "Vitor"]
SOBRENOMES = ["Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira", "Lima", "Gomes", "Costa", "Ribeiro", "Martins", "Carvalho", "Almeida"]

PRODUTOS = [
    ("ITAU-INV-01", "CDB Itaú Personalizado Pós-Fixado", "Investimentos", "104% a 112% do CDI", "Liquidez Diária ou 360 dias", 400, "Garantia FGC e rentabilidade progressiva", 92, 88),
    ("ITAU-CRED-02", "Crédito Sob Medida com Taxa Bonificada", "Crédito & Fluxo", "A partir de 1,19% a.m.", "Até 90 dias para 1ª parcela", 300, "Sem cobrança de TAC e contratação 100% digital", 85, 90),
    ("ITAU-CARD-03", "Cartão Itaú Carbon Platinum / Black", "Meios de Pagamento", "Pontos Átomos ou 1,5% Cashback", "Anuidade isenta por gastos", 600, "Acesso a salas VIP e tag de pedágio", 94, 91),
    ("ITAU-PREV-04", "Previdência & Planejamento Sucessório", "Previdência", "Taxa zero de custódia", "PGBL / VGBL a partir de R$ 100/mês", 500, "Dedução de até 12% da renda bruta no IRPF", 89, 82),
    ("ITAU-PROT-05", "Seguro Vida & Proteção Integrada", "Seguros", "A partir de R$ 19,90/mês", "Vigência imediata", 200, "Telemedicina Einstein 24h e assistência funeral", 96, 84),
]


def gerar_clientes():
    """Os 1.000 clientes com regra determinística (ID % 2 == 0 -> F, ID % 2 != 0 -> M)."""
    clientes = []
    for cid in range(1, 1001):
        is_f = (cid % 2 == 0)
        genero = 'F' if is_f else 'M'
        primeiro_nome = NOMES_F[(cid // 2) % len(NOMES_F)] if is_f else NOMES_M[((cid - 1) // 2) % len(NOMES_M)]
        sobrenome = SOBRENOMES[(cid * 7) % len(SOBRENOMES)]

        score = min(1000, max(120, ((cid * 37) % 850) + 150))
        if score >= 750:
            corte = 'ALTA_PROPENSAO'
            seg = 'Itaú Personnalité' if score > 850 else 'Itaú Uniclass'
            diretriz = 'Abordagem consultiva, sofisticada e proativa.'
        elif score >= 450:
            corte = 'MEDIA_PROPENSAO'
            seg = 'Itaú Uniclass'
            diretriz = 'Abordagem equilibrada e orientada a metas.'
        else:
            corte = 'BAIXA_PROPENSAO'
            seg = 'Itaú Varejo'
            diretriz = 'Abordagem didática, acolhedora e de alívio financeiro.'

        saldo = round(1500.0 + ((score * 28.5) % 45000), 2)
        limite = round(2000.0 + ((score * 35.0) % 65000), 2)

        clientes.append(ClienteRegistro(
            cliente_id=cid,
            nome=f"{primeiro_nome} {sobrenome}",
            primeiro_nome=primeiro_nome,
            genero=genero,
            score_comportamental=score,
            indice_corte=corte,
            segmento=seg,
            saldo_estimado=Decimal(str(saldo)),
            limite_cartao=Decimal(str(limite)),
            diretriz_comportamental=diretriz,
        ))
    return clientes


def popular():
    saudacao = "Que bom ter você aqui,[VARIAVEL_NOME] !"
    p1 = "Hoje, seu dinheiro está concentrado no presente, deixando pouco espaço para imprevistos e planos futuros."
    p2 = "Pequenas mudanças podem trazer mais equilíbrio. Você já sabe onde está, chegou a hora de decidir seu próximo passo."

    with transaction.atomic():
        AuditoriaFluxoConfig.objects.update_or_create(
            codigo_fluxo='FLUXO_AUDITORIA_PADRAO',
            defaults={
                "saudacao_template": saudacao,
                "texto_1_neutro_p1": p1, "texto_1_neutro_p2": p2,        # TEXTO_1[NEUTRO]
                "texto_2_masculino_p1": p1, "texto_2_masculino_p2": p2,  # TEXTO_2[MASCULINO]
                "texto_3_feminino_p1": p1, "texto_3_feminino_p2": p2,    # TEXTO_3[FEMININO]
                "botao_proximo": 'E agora?',
            },
        )

        for codigo, produto, categoria, taxa, carencia, score_min, beneficio, af_f, af_m in PRODUTOS:
            PlanilhaProdutoRegistro.objects.update_or_create(
                codigo=codigo,
                defaults={
                    "produto": produto, "categoria": categoria, "taxa_ou_retorno": taxa,
                    "carencia_prazo": carencia, "score_minimo": score_min, "beneficio_chave": beneficio,
                    "afinidade_f": af_f, "afinidade_m": af_m,
                },
            )

        campos = ["nome", "primeiro_nome", "genero", "score_comportamental", "indice_corte",
                  "segmento", "saldo_estimado", "limite_cartao", "diretriz_comportamental"]
        ClienteRegistro.objects.bulk_create(
            gerar_clientes(), update_conflicts=True, unique_fields=["cliente_id"], update_fields=campos,
        )

        FeatureFlagInteracaoTelaIAI.objects.get_or_create(
            codigo="CHAVE_INTEIRACAO_TELA_IAI", defaults={"chave_ativa": True},
        )


def init_db():
    print(f"Banco de dados: {settings.DATABASES['default']['NAME']}")
    print("1/2 migrate (esquema vem das migrações Django)")
    call_command("migrate", interactive=False, verbosity=1)
    print("2/2 população (fluxo de auditoria, 5 produtos, 1.000 clientes, chave ON/OFF)")
    popular()
    total = ClienteRegistro.objects.count()
    if total != 1000:
        raise SystemExit(f"Esperados 1.000 clientes, o banco tem {total}.")
    print(f"Banco de dados inicializado e populado: {total} clientes, "
          f"{PlanilhaProdutoRegistro.objects.count()} produtos, "
          f"chave inteiração-tela-iai = {'ON' if FeatureFlagInteracaoTelaIAI.objects.get(pk='CHAVE_INTEIRACAO_TELA_IAI').chave_ativa else 'OFF'}.")


if __name__ == '__main__':
    init_db()
