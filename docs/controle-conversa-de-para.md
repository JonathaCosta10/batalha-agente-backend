# Controle da conversa — de-para do inventário do front para o roteiro

**Fonte.** `frontend-agent-conversacional/docs/integracao/falas-fixas.md`, commit `1ca06b5` do front (188 linhas em 13 tabelas). Pedidos B1, B2 e C10 de `docs/integracao/pendencias.md`. Roteiro `2026-09-27.2` → `2026-09-27.3` (`apps/context_agent_datadriven/conversa/roteiro.json`). Gerado em 2026-09-27 pelo script do de-para (lê o inventário e o roteiro; nada à mão na tabela).

## Resumo

| medida | valor |
|---|---|
| linhas do inventário | 188 (189 ids: `card.alt_itau` / `card.alt_iagora` dividem uma linha) |
| novas no roteiro | 161 |
| já presentes (reuso do id existente) | 25 |
| JÁ REGISTRADAS (reuso) | 3 |
| falas compostas antigas mantidas e marcadas `substituido_por` (fundidas) | 16 |
| falas no roteiro, antes → depois | 45 → 206 |
| textos alterados no reuso | 8 |

Cada fala do roteiro leva `inventario_front: [...]` com o(s) id(s) do inventário que cobre; `tests/test_controle_conversa.py` confere 189 ids, sem repetição.

**Estágios novos:** `acompanhe`, `folha`, `toast`, `png`, `nav`, `global`. A validação (`carregar_roteiro`) lê `roteiro["estagios"]` do próprio JSON — sem lista fixa no código.

**Variáveis novas:** `falta_apos_cortes`, `n`, `total`, `inflow_mensal`, `periodo_base`, `necessario_para_surplus_15`, `gasto_atual`, `lancamentos_na_janela`, `regra_nivel`, `linha_de_corte`, `linha_de_corte_ddmm`, `ate_linha_de_corte`, `regra`, `fonte`, `medido_em`, `secao`. `genero` passou a ter `fonte_alvo` perfil-usuario `usuario.genero`.

## Renomeação de variáveis (inventário → roteiro)

| inventário | roteiro | onde |
|---|---|---|
| `{nome}` | `{primeiro_nome}` | `home.saudacao`, `chat.titulo`, `bot.intro`, `bot.apoio_negativado`, `bot.finish`, `bot.fallback` |
| `{saldo_mensal_medio}` | `{surplus_mensal}` | `bot.apoio_negativado.leitura_medida` |
| `{saldo}` | `{saldo_exibido}` | `bot.apoio_negativado.leitura_local` |
| `{periodo}` | `{periodo_base}` | `confirm.proposta.raciocinio_renda`, `confirm.proposta.item_raciocinio`, `confirm.proposta.rodape` |
| `{lancamentos}` | `{lancamentos_na_janela}` | `confirm.proposta.item_raciocinio` |
| `{dd/mm}` | `{linha_de_corte_ddmm}` | `confirm.proposta.item_ate_corte` |
| `{dd/mm/aaaa}` | `{linha_de_corte}` | `confirm.proposta.rodape` |
| `{frase}` | `{frase_card}` | `card.aria_previa` |

## Textos alterados no reuso

| id do roteiro | antes (2026-09-27.2) | agora (texto exato do front) |
|---|---|---|
| `home.aviso_plano` | Um espaço para planejar. Os valores são estimativas. Você decide quais compromissos assumi… | {"titulo": "Um espaço para planejar", "corpo": "Os valores vêm dos seus registros até agor… |
| `bot.convite_50_30_20` | Agora vamos transformar essa oportunidade em um plano.⏎⏎Vamos usar a regra *50-30-20* como… | Agora vamos transformar essa oportunidade em um plano.⏎⏎Vamos usar a regra *50-30-20* como… |
| `bot.confirm` | Confira os compromissos de exemplo para janeiro de 2026: | Confira os compromissos para janeiro de 2026, calculados sobre os seus registros até agora… |
| `confirm.aviso_estimativa` | Estimativas para janeiro, não gastos já realizados… | Estimativas para janeiro, não gastos já realizados. Só serão registradas se você confirmar… |
| `confirm.compromisso.delivery` | Limitar delivery a {delivery_meta} em janeiro. | Limitar delivery a {meta} em janeiro. |
| `confirm.compromisso.compras` | Limitar compras por impulso a {compras_meta}… | Limitar compras por impulso a {meta} em janeiro. |
| `confirm.compromisso.outros` | Reduzir {outros_corte} em outros gastos flexíveis… | Reduzir {corte} em outros gastos flexíveis em janeiro. |
| `confirm.compromisso.reserva` | Separar {reserva} para imprevistos… | Separar {reserva} para imprevistos em janeiro. |
| `card.frase.reserva.0` (nova) | front: "…mais preparada." para qualquer gênero | `{"F": "…preparada.", "M": "…preparado."}`, `variaveis: ["genero"]` |

## Composições antigas → falas novas (fundidas)

Mantidas no roteiro por compatibilidade (apps/conversas lê `home.visao_conta.*`, `intro.carrossel.1`, `card.frases` pelo id), com `substituido_por`:

- `home.atalhos` → `nav.atalho.pix`, `nav.atalho.pagar`, `nav.atalho.cartoes`, `nav.atalho.planejar`
- `home.visao_conta.titulo` → `home.saldo.eyebrow`, `home.saldo.periodo`
- `home.visao_conta.saldo` → `home.saldo.titulo`, `home.saldo.valor`
- `home.visao_conta.entradas` → `home.saldo.entradas`
- `home.visao_conta.saidas` → `home.saldo.saidas`
- `chat.cabecalho` → `chat.titulo`, `chat.subtitulo_cabecalho`
- `intro.carrossel.1` → `intro.carrossel.1.rotulo`, `intro.carrossel.1.titulo`, `intro.carrossel.1.corpo`
- `intro.carrossel.2` → `intro.carrossel.2.rotulo`, `intro.carrossel.2.titulo`, `intro.carrossel.2.corpo`
- `confirm.painel_titulo` → `confirm.painel.eyebrow`, `confirm.painel.titulo`
- `card.imagem` → `confirm.painel.eyebrow`, `png.simbolo`, `card.frase.*`, `card.tagline`, `card.convite`, `card.alt_itau`, `card.alt_iagora`
- `card.frases` → `card.frase.delivery.0`, `card.frase.delivery.1`, `card.frase.delivery.2`, `card.frase.compras.0`, `card.frase.compras.1`, `card.frase.compras.2`, `card.frase.reserva.0`, `card.frase.reserva.1`, `card.frase.reserva.2`, `card.frase.outros.0`, `card.frase.outros.1`, `card.frase.outros.2`
- `card.botoes` → `card.salvar`, `card.preparando`, `card.baixar`, `card.outra_frase`, `card.voltar`
- `finish.painel` → `finish.titulo`, `finish.texto`, `finish.voltar`
- `livre.composer` → `livre.composer.placeholder`, `livre.composer.aria`, `livre.composer.aria_enviar`, `livre.composer.rodape`
- `livre.respostas` → `bot.saldo`, `bot.valores`, `bot.humano`, `bot.humano_negativado`, `bot.fallback`
- `sistema.reiniciar` → `folha.reset.titulo`, `folha.reset.texto`, `folha.reset.confirmar`, `folha.reset.manter`, `toast.reiniciado`

## B2 — frase da reserva e fallbacks da proposta

`confirm.painel.corte_insuficiente` ("reserva de 15% da renda") e `confirm.proposta.*` (raciocínio, item, até-a-linha-de-corte, níveis, período NAO_MEDIDO, rodapé — `planApi.ts:23-72`) são `tipo: template` com `uso: "fallback quando plano/proposta falha; o backend já devolve apresentacao.*"`.

## Formato na rota

`GET controle-conversa/` devolve, além do que já devolvia, `versao_roteiro` no topo e em cada fala, e `variaveis: []` quando a fala não tem variável: `{id, estagio, texto, variaveis[], versao_roteiro, …}`. `texto` pode ser string, lista ou objeto (`{titulo, corpo}`, `{rotulo, valor}`, `{rotulo, exibido}`, `{F, M}`).

## Alertas acrescentados (pedido da sessão back-32)

- `bot.convite_50_30_20`: o front reconhece a bolha por igualdade de texto (`isInvite`); deve usar etapa/id.
- `bot.intro`, `bot.finish`: têm `!`; tom T3 Vulnerável sem exclamação (texto mantido).
- `home.visao_conta.titulo`, `home.saldo.periodo`: rótulo "Dezembro/25", mas o mês medido é nov/2025.
- AgoraTrigger sem id → `intro.gatilho_agora` (mesmo id da ação em apps/conversas); BOT.values/balance/human → `bot.valores`/`bot.saldo`/`bot.humano`; FollowUp → `acompanhe.*`; AssistantFab → `home.aria_fab`, `home.fab_selo`.
- Linhas com número calculado no front levam `alerta: "valor local no front — deve vir de rota com selo (<rota>)"`.
- A frase fixa de encaminhamento humano (consolidação) e a resposta fixa fora de contexto de apps/conversas **não estão no inventário do front**; não foram registradas (dono: back-32, `conversas/interacao`).

## Tabela inventário → roteiro

| # | inventário | roteiro | situação |
|---|---|---|---|
| 1 | `home.saudacao` | `home.saudacao` | já presente (reuso) |
| 1 | `home.subsaudacao` | `home.convite` | já presente (reuso) |
| 1 | `home.botao_conferir` | `home.botao_conferir` | já presente (reuso) |
| 1 | `home.rotulo_conta` | `home.conta_rotulo` | já presente (reuso) |
| 1 | `home.aria_buscar` | `home.aria_buscar` | nova |
| 1 | `home.aria_avisos` | `home.aria_avisos` | nova |
| 1 | `home.aria_abrir_conversa` | `home.aria_abrir_conversa` | nova |
| 1 | `home.titulo_conta` | `home.titulo_conta` | nova |
| 1 | `home.alt_marca_itau` | `home.alt_marca_itau` | nova |
| 1 | `home.aria_mostrar_saldo` | `home.aria_mostrar_saldo` | nova |
| 1 | `home.aria_ocultar_saldo` | `home.aria_ocultar_saldo` | nova |
| 1 | `home.conta_corrente` | `home.conta_corrente` | nova |
| 1 | `saldo.aria` | `home.saldo.aria` | nova |
| 1 | `saldo.eyebrow` | `home.saldo.eyebrow` | nova |
| 1 | `saldo.periodo` | `home.saldo.periodo` | nova |
| 1 | `saldo.titulo` | `home.saldo.titulo` | nova |
| 1 | `saldo.valor` | `home.saldo.valor` | nova |
| 1 | `saldo.entradas` | `home.saldo.entradas` | nova |
| 1 | `saldo.saidas` | `home.saldo.saidas` | nova |
| 1 | `saldo.oculto` | `home.saldo.oculto` | nova |
| 1 | `home.acompanhe` | `home.acompanhe` | nova |
| 1 | `home.alt_marca_iagora` | `home.alt_marca_iagora` | nova |
| 1 | `home.aviso_plano` | `home.aviso_plano` | já presente (reuso) |
| 1 | `home.aviso_negativado` | `home.aviso_negativado` | JÁ REGISTRADA (reuso) |
| 1 | `home.recomecar` | `home.botao_recomecar` | já presente (reuso) |
| 1 | `home.aria_fab` | `home.aria_fab` | nova |
| 1 | `home.fab_selo` | `home.fab_selo` | nova |
| 2 | `chat.titulo` | `chat.titulo` | nova |
| 2 | `chat.subtitulo` | `chat.subtitulo_cabecalho` | nova |
| 2 | `chat.reiniciar` | `chat.botao_reiniciar` | já presente (reuso) |
| 2 | `chat.aria_reiniciar` | `chat.aria_reiniciar` | nova |
| 2 | `chat.aria_fechar` | `chat.aria_fechar` | nova |
| 2 | `chat.divisor` | `chat.subtitulo` | já presente (reuso) |
| 2 | `bot.intro` | `bot.intro` | já presente (reuso) |
| 2 | `bot.apoio_negativado` | `bot.apoio_negativado` | JÁ REGISTRADA (reuso) |
| 2 | `bot.apoio_negativado.leitura_medida` | `bot.apoio_negativado.leitura_medida` | nova |
| 2 | `bot.apoio_negativado.leitura_local` | `bot.apoio_negativado.leitura_local` | nova |
| 2 | `intro.card1.rotulo` | `intro.carrossel.1.rotulo` | nova |
| 2 | `intro.card1.titulo` | `intro.carrossel.1.titulo` | nova |
| 2 | `intro.card1.corpo` | `intro.carrossel.1.corpo` | nova |
| 2 | `intro.card2.rotulo` | `intro.carrossel.2.rotulo` | nova |
| 2 | `intro.card2.titulo` | `intro.carrossel.2.titulo` | nova |
| 2 | `intro.card2.corpo` | `intro.carrossel.2.corpo` | nova |
| 2 | `intro.carrossel_dica` | `intro.dica_arraste` | já presente (reuso) |
| 2 | `intro.aria_carrossel` | `intro.aria_carrossel` | nova |
| 2 | `intro.aria_trilho` | `intro.aria_trilho` | nova |
| 2 | `intro.aria_slide` | `intro.aria_slide` | nova |
| 2 | `intro.aria_progresso` | `intro.aria_progresso` | nova |
| 2 | `intro.aria_ver_card` | `intro.aria_ver_card` | nova |
| 2 | `intro.aria_agora` | `intro.gatilho_agora` | nova |
| 3 | `bot.convite` | `bot.convite_50_30_20` | já presente (reuso) |
| 3 | `bot.convite_anterior` | `bot.convite_anterior` | nova |
| 3 | `user.topo_desafio` | `user.topo_desafio` | já presente (reuso) |
| 4 | `bot.confirm` | `bot.confirm` | já presente (reuso) |
| 4 | `painel.eyebrow` | `confirm.painel.eyebrow` | nova |
| 4 | `painel.titulo` | `confirm.painel.titulo` | nova |
| 4 | `painel.resumo` | `confirm.resumo` | já presente (reuso) |
| 4 | `painel.corte_insuficiente` | `confirm.painel.corte_insuficiente` | nova |
| 4 | `painel.livre_sem_corte` | `confirm.painel.livre_sem_corte` | nova |
| 4 | `painel.aviso_proposta` | `confirm.painel.aviso_proposta` | nova |
| 4 | `painel.aviso_exemplo` | `confirm.aviso_estimativa` | já presente (reuso) |
| 4 | `painel.selo_backend_indisponivel` | `confirm.painel.selo_backend_indisponivel` | nova |
| 4 | `painel.selo_exemplo` | `confirm.painel.selo_exemplo` | nova |
| 4 | `compromisso.delivery` | `confirm.compromisso.delivery` | já presente (reuso) |
| 4 | `compromisso.shopping` | `confirm.compromisso.compras` | já presente (reuso) |
| 4 | `compromisso.other` | `confirm.compromisso.outros` | já presente (reuso) |
| 4 | `compromisso.reserve` | `confirm.compromisso.reserva` | já presente (reuso) |
| 4 | `proposta.raciocinio_renda` | `confirm.proposta.raciocinio_renda` | nova |
| 4 | `proposta.raciocinio_meta15` | `confirm.proposta.raciocinio_meta15` | nova |
| 4 | `proposta.item_raciocinio` | `confirm.proposta.item_raciocinio` | nova |
| 4 | `proposta.item_ate_corte` | `confirm.proposta.item_ate_corte` | nova |
| 4 | `proposta.nivel1` | `confirm.proposta.nivel1` | nova |
| 4 | `proposta.nivel2` | `confirm.proposta.nivel2` | nova |
| 4 | `proposta.periodo_nao_medido` | `confirm.proposta.periodo_nao_medido` | nova |
| 4 | `proposta.rodape` | `confirm.proposta.rodape` | nova |
| 4 | `user.assumir` | `user.assumir` | já presente (reuso) |
| 4 | `user.ajustar` | `user.ajustar` | já presente (reuso) |
| 4 | `bot.adjust` | `bot.adjust` | nova |
| 5 | `bot.card` | `bot.card` | já presente (reuso) |
| 5 | `card.titulo` | `card.titulo` | já presente (reuso) |
| 5 | `card.aviso` | `card.privacidade` | já presente (reuso) |
| 5 | `card.salvar` | `card.salvar` | nova |
| 5 | `card.preparando` | `card.preparando` | nova |
| 5 | `card.baixar` | `card.baixar` | nova |
| 5 | `card.outra_frase` | `card.outra_frase` | nova |
| 5 | `card.voltar_sem_salvar` | `card.voltar` | nova |
| 5 | `card.aria_previa` | `card.aria_previa` | nova |
| 5 | `card.alt_itau` | `card.alt_itau` | nova |
| 5 | `card.alt_iagora` | `card.alt_iagora` | nova |
| 6 | `user.salvar_imagem` | `user.salvar_imagem` | nova |
| 6 | `bot.finish` | `bot.finish` | já presente (reuso) |
| 6 | `fim.titulo` | `finish.titulo` | nova |
| 6 | `fim.texto` | `finish.texto` | nova |
| 6 | `fim.voltar` | `finish.voltar` | nova |
| 7 | `bot.saldo` | `bot.saldo` | nova |
| 7 | `bot.valores` | `bot.valores` | nova |
| 7 | `bot.humano` | `bot.humano` | nova |
| 7 | `bot.humano_negativado` | `bot.humano_negativado` | JÁ REGISTRADA (reuso) |
| 7 | `bot.fallback` | `bot.fallback` | nova |
| 7 | `composer.placeholder` | `livre.composer.placeholder` | nova |
| 7 | `composer.aria` | `livre.composer.aria` | nova |
| 7 | `composer.aria_enviar` | `livre.composer.aria_enviar` | nova |
| 7 | `composer.rodape` | `livre.composer.rodape` | nova |
| 7 | `chat.aria_digitando` | `livre.aria_digitando` | nova |
| 8 | `acomp.alt_cabecalho` | `acompanhe.alt_cabecalho` | nova |
| 8 | `acomp.kicker` | `acompanhe.kicker` | nova |
| 8 | `acomp.voltar` | `acompanhe.voltar` | nova |
| 8 | `acomp.aria_voltar` | `acompanhe.aria_voltar` | nova |
| 8 | `acomp.titulo` | `acompanhe.titulo` | nova |
| 8 | `acomp.subtitulo` | `acompanhe.subtitulo` | nova |
| 8 | `acomp.progresso_rotulo` | `acompanhe.progresso_rotulo` | nova |
| 8 | `acomp.progresso_titulo` | `acompanhe.progresso_titulo` | nova |
| 8 | `acomp.progresso_texto` | `acompanhe.progresso_texto` | nova |
| 8 | `acomp.progresso_nota` | `acompanhe.progresso_nota` | nova |
| 8 | `acomp.secao_titulo` | `acompanhe.secao_titulo` | nova |
| 8 | `acomp.secao_texto` | `acompanhe.secao_texto` | nova |
| 8 | `acomp.contagem_1` | `acompanhe.contagem_1` | nova |
| 8 | `acomp.contagem_n` | `acompanhe.contagem_n` | nova |
| 8 | `acomp.aria_lista` | `acompanhe.aria_lista` | nova |
| 8 | `acomp.vazio_titulo` | `acompanhe.vazio_titulo` | nova |
| 8 | `acomp.vazio_texto` | `acompanhe.vazio_texto` | nova |
| 8 | `categoria.delivery` | `acompanhe.categoria.delivery` | nova |
| 8 | `categoria.shopping` | `acompanhe.categoria.compras` | nova |
| 8 | `categoria.reserve` | `acompanhe.categoria.reserva` | nova |
| 8 | `categoria.other` | `acompanhe.categoria.outros` | nova |
| 8 | `acomp.retomar_titulo` | `acompanhe.retomar_titulo` | nova |
| 8 | `acomp.retomar_texto` | `acompanhe.retomar_texto` | nova |
| 8 | `acomp.aria_retomar` | `acompanhe.aria_retomar` | nova |
| 9 | `png.periodo` | `png.periodo` | nova |
| 9 | `png.simbolo` | `png.simbolo` | nova |
| 9 | `card.tagline` | `card.tagline` | nova |
| 9 | `card.convite` | `card.convite` | nova |
| 9 | `png.titulo_compartilhar` | `png.titulo_compartilhar` | nova |
| 9 | `png.arquivo` | `png.arquivo` | nova |
| 9 | `card.frase.delivery.0` | `card.frase.delivery.0` | nova |
| 9 | `card.frase.delivery.1` | `card.frase.delivery.1` | nova |
| 9 | `card.frase.delivery.2` | `card.frase.delivery.2` | nova |
| 9 | `card.frase.shopping.0` | `card.frase.compras.0` | nova |
| 9 | `card.frase.shopping.1` | `card.frase.compras.1` | nova |
| 9 | `card.frase.shopping.2` | `card.frase.compras.2` | nova |
| 9 | `card.frase.reserve.0` | `card.frase.reserva.0` | nova |
| 9 | `card.frase.reserve.1` | `card.frase.reserva.1` | nova |
| 9 | `card.frase.reserve.2` | `card.frase.reserva.2` | nova |
| 9 | `card.frase.other.0` | `card.frase.outros.0` | nova |
| 9 | `card.frase.other.1` | `card.frase.outros.1` | nova |
| 9 | `card.frase.other.2` | `card.frase.outros.2` | nova |
| 10 | `folha.aria_fechar` | `folha.aria_fechar` | nova |
| 10 | `folha.reset.aria` | `folha.reset.aria` | nova |
| 10 | `folha.eyebrow` | `folha.eyebrow` | nova |
| 10 | `folha.reset.titulo` | `folha.reset.titulo` | nova |
| 10 | `folha.reset.texto` | `folha.reset.texto` | nova |
| 10 | `folha.reset.confirmar` | `folha.reset.confirmar` | nova |
| 10 | `folha.reset.manter` | `folha.reset.manter` | nova |
| 10 | `folha.info.titulo` | `folha.info.titulo` | nova |
| 10 | `folha.info.texto` | `folha.info.texto` | nova |
| 10 | `folha.conversar` | `folha.conversar` | nova |
| 10 | `folha.plano.titulo` | `folha.plano.titulo` | nova |
| 10 | `folha.plano.texto` | `folha.plano.texto` | nova |
| 10 | `folha.plano.resumo` | `folha.plano.resumo` | nova |
| 10 | `folha.plano.ver_card` | `folha.plano.ver_card` | nova |
| 10 | `folha.plano.ver_conversa` | `folha.plano.ver_conversa` | nova |
| 10 | `folha.vazio.titulo` | `folha.vazio.titulo` | nova |
| 10 | `folha.vazio.texto` | `folha.vazio.texto` | nova |
| 11 | `toast.avisos` | `toast.avisos` | nova |
| 11 | `toast.compartilhado` | `toast.compartilhado` | nova |
| 11 | `toast.baixado` | `toast.baixado` | nova |
| 11 | `toast.cancelado` | `toast.cancelado` | nova |
| 11 | `toast.falha_exportar` | `toast.falha_exportar` | nova |
| 11 | `toast.reiniciado` | `toast.reiniciado` | nova |
| 11 | `toast.erro_marca` | `toast.erro_marca` | nova |
| 11 | `toast.erro_navegador` | `toast.erro_navegador` | nova |
| 11 | `toast.erro_png` | `toast.erro_png` | nova |
| 12 | `nav.inicio` | `nav.inicio` | nova |
| 12 | `nav.extrato` | `nav.extrato` | nova |
| 12 | `nav.pagamentos` | `nav.pagamentos` | nova |
| 12 | `nav.pra_voce` | `nav.pra_voce` | nova |
| 12 | `nav.menu` | `nav.menu` | nova |
| 12 | `nav.aria` | `nav.aria` | nova |
| 12 | `atalho.pix` | `nav.atalho.pix` | nova |
| 12 | `atalho.pagar` | `nav.atalho.pagar` | nova |
| 12 | `atalho.cartoes` | `nav.atalho.cartoes` | nova |
| 12 | `atalho.planejar` | `nav.atalho.planejar` | nova |
| 12 | `atalho.aria` | `nav.atalho.aria` | nova |
| 12 | `atalho.busca` | `nav.atalho.busca` | nova |
| 13 | `erro.titulo` | `global.erro.titulo` | nova |
| 13 | `erro.texto` | `global.erro.texto` | nova |
| 13 | `erro.tentar` | `global.erro.tentar` | nova |
| 13 | `doc.titulo` | `global.doc.titulo` | nova |
| 13 | `doc.descricao` | `global.doc.descricao` | nova |
