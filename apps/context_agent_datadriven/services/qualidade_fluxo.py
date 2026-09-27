"""Controles factuais do fluxo da demo, independentes do texto da resposta."""


def verificar_fluxo(cliente, chat, comunicacao):
    ativo = chat["chat_variavel_1"]["texto_ativo"]
    tag_esperada = ("TEXTO_1[NEUTRO]" if chat["chave_interacao_tela_iai"] == "ON" else
                    "TEXTO_3[FEMININO]" if cliente["genero"] == "F" else "TEXTO_2[MASCULINO]")
    score = cliente["score_comportamental"]
    produtos = comunicacao["planilha_fixa"]
    return {
        "mesmo_cliente_nas_tres_rotas": cliente["id"] == chat["cliente"]["id"] == comunicacao["cliente"]["id"],
        "nome_confere": cliente["nome"] == chat["cliente"]["nome"] == comunicacao["cliente"]["nome"],
        "tag_respeita_chave_e_genero": ativo["tag"] == tag_esperada,
        "texto_exibido_confere": chat["chat_variavel_1"]["mensagem_abertura"] == ativo["texto_completo"],
        "botao_do_fluxo": chat["chat_variavel_1"]["botao_proximo"] == "E agora?",
        "template_3_confere": comunicacao["template_id"] == "TEMPLATE_3_FIXED_SPREADSHEET",
        "score_interno_coerente": score == comunicacao["cliente"]["score_comportamental"],
        "elegibilidade_coerente": all(
            (score >= item["score_minimo"]) == (item["status_elegibilidade"] == "Pré-Aprovado")
            for item in produtos
        ),
    }
