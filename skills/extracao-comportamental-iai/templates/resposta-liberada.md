# Resposta liberada (só após APROVADO)

O texto vem de `resposta_liberada.modelo_de_texto` no contrato, preenchido pelo guard com os valores RELIDOS:

    {"aprovado": true, "id_extracao": "<id da evidência>", "numero_usuario": <int>,
     "id_usuario": "<UUID>", "resposta": "Usuário sorteado nº ... Quer explorar esse movimento?"}

Nunca copie texto do agente para `resposta`. Em `REPROVADO` ou `NAO_MEDIDO` nada é impresso para o usuário.
