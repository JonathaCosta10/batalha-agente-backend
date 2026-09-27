"""
Models do Banco de Dados para o Sistema de Auditoria e Recomendação Itaú.
Projeto: desafio-itau-batalha-de-agentes-time2
"""

from django.db import models

class FeatureFlagInteracaoTelaIAI(models.Model):
    """
    Chave ON - OFF do Backend Django para o ponto de 'inteiração-tela-iai'.
    Quando 'chave_ativa' estiver ON (True):
      -> Liga o modo 'Neutro' como padrão para ambos os gêneros
      Exemplo:
        'Que bom ter você aqui, Maria!' (F)
        Hoje, seu dinheiro está concentrado no presente, deixando pouco espaço para imprevistos e planos futuros.
        Pequenas mudanças podem trazer mais equilíbrio. Você já sabe onde está, chegou a hora de decidir seu próximo passo.

        'Que bom ter você aqui, Joao!' (M)
        Hoje, seu dinheiro está concentrado no presente, deixando pouco espaço para imprevistos e planos futuros.
        Pequenas mudanças podem trazer mais equilíbrio. Você já sabe onde está, chegou a hora de decidir seu próximo passo.
    Quando estiver OFF (False):
      -> Segue o fluxo segmentado por gênero F e M (TEXTO_3[FEMININO] / TEXTO_2[MASCULINO]).
    """
    codigo = models.CharField(max_length=60, primary_key=True, default="CHAVE_INTEIRACAO_TELA_IAI")
    nome = models.CharField(max_length=120, default="Ponto de Inteiração Tela-IAI")
    chave_ativa = models.BooleanField(
        default=True,
        help_text="Chave ON (True) / OFF (False). Quando ligada (ON), ativa o modo Neutro padrão."
    )
    descricao = models.TextField(
        default="Controla se a tela de auditoria aplica o template Neutro universal ou mantém bifurcação estrita."
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        status_txt = "ON" if self.chave_ativa else "OFF"
        return f"{self.codigo}: {status_txt}"

class AuditoriaFluxoConfig(models.Model):
    """
    Configuração e fluxo de mensagens da auditoria com as variáveis solicitadas:
    - Saudação: "Que bom ter você aqui,[VARIAVEL_NOME] !"
    - TEXTO_1[NEUTRO]
    - TEXTO_2[MASCULINO]
    - TEXTO_3[FEMININO]
    - Botão de ação: "E agora?"
    """
    codigo_fluxo = models.CharField(max_length=50, unique=True, default="FLUXO_AUDITORIA_PADRAO")
    saudacao_template = models.CharField(
        max_length=255,
        default="Que bom ter você aqui,[VARIAVEL_NOME] !"
    )
    
    # TEXTO_1[NEUTRO]
    texto_1_neutro_p1 = models.TextField(
        default="Hoje, seu dinheiro está concentrado no presente, deixando pouco espaço para imprevistos e planos futuros."
    )
    texto_1_neutro_p2 = models.TextField(
        default="Pequenas mudanças podem trazer mais equilíbrio. Você já sabe onde está, chegou a hora de decidir seu próximo passo."
    )

    # TEXTO_2[MASCULINO]
    texto_2_masculino_p1 = models.TextField(
        default="Hoje, seu dinheiro está concentrado no presente, deixando pouco espaço para imprevistos e planos futuros."
    )
    texto_2_masculino_p2 = models.TextField(
        default="Pequenas mudanças podem trazer mais equilíbrio. Você já sabe onde está, chegou a hora de decidir seu próximo passo."
    )

    # TEXTO_3[FEMININO]
    texto_3_feminino_p1 = models.TextField(
        default="Hoje, seu dinheiro está concentrado no presente, deixando pouco espaço para imprevistos e planos futuros."
    )
    texto_3_feminino_p2 = models.TextField(
        default="Pequenas mudanças podem trazer mais equilíbrio. Você já sabe onde está, chegou a hora de decidir seu próximo passo."
    )

    botao_proximo = models.CharField(max_length=50, default="E agora?")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def formatar_saudacao(self, nome_cliente: str) -> str:
        return self.saudacao_template.replace("[VARIAVEL_NOME]", nome_cliente).replace("{VARIAVEL_NOME}", nome_cliente)

    def __str__(self):
        return f"{self.codigo_fluxo} - {self.saudacao_template}"

class ClienteRegistro(models.Model):
    """
    Tabela de clientes persistida no banco SQLite (recorte de 1.000 clientes).
    Regra de negócio: ID % 2 == 0 -> Feminino ('F'), ID % 2 != 0 -> Masculino ('M').
    """
    cliente_id = models.IntegerField(primary_key=True)
    nome = models.CharField(max_length=150)
    primeiro_nome = models.CharField(max_length=80)
    genero = models.CharField(max_length=1, choices=[('F', 'Feminino'), ('M', 'Masculino')])
    score_comportamental = models.IntegerField(default=500)
    indice_corte = models.CharField(max_length=50)
    segmento = models.CharField(max_length=50, default='Itaú Varejo')
    saldo_estimado = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    limite_cartao = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    diretriz_comportamental = models.TextField(blank=True)

    class Meta:
        # Nome fixo: services/customer_repository.py lê esta tabela com SQL cru.
        db_table = 'recomendacao_clienteregistro'

    def __str__(self):
        return f"#{self.cliente_id} {self.nome} ({self.genero}) - Score: {self.score_comportamental}"

class PlanilhaProdutoRegistro(models.Model):
    """
    Tabela da Matriz Fixa de Produtos do Itaú (Template 3).
    """
    codigo = models.CharField(max_length=50, primary_key=True)
    produto = models.CharField(max_length=150)
    categoria = models.CharField(max_length=100)
    taxa_ou_retorno = models.CharField(max_length=100)
    carencia_prazo = models.CharField(max_length=100)
    score_minimo = models.IntegerField(default=0)
    beneficio_chave = models.TextField()
    afinidade_f = models.IntegerField(default=85)
    afinidade_m = models.IntegerField(default=85)

    def __str__(self):
        return f"{self.codigo} - {self.produto}"
