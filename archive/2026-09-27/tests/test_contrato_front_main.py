# Arquivado em 2026-09-27 (P0 do dono, identidade só por id_usuario): versão inteira de tests/test_contrato_front_main.py
# de antes da migração. test_proposta_tem_tudo_que_planApi_le mandava {"ref": 1} e afirmava usuario.indice == 1
# ("Maria, id 0 no front -> ref 1"): o índice posicional como identidade. A versão viva manda o UUID e afirma
# usuario.id_usuario. Não virou prova negativa porque i-agora/plano/proposta (services/usuario_real.resolver)
# ainda aceita índice; o P0 só mudou perfil_usuario, e o código de produção não foi tocado.

"""Encaixe front <-> back: as duas rotas que o front `frontend-agent-conversacional` (branch main) chama.

O front lê estes campos sem fallback (quebram a tela se faltarem):
- src/services/planApi.ts    POST i-agora/plano/proposta/ {"ref": n}
- src/services/balanceApi.ts GET  usuario-real/<ref>/saldo-mes/
Este teste percorre a resposta HTTP real (executor BigQuery falso, sem rede) e confere cada campo e tipo.
Prova negativa: `faltas()` tem de acusar um corpo sem `totais.valor_liberado` e um `nivel` fora de "Nível N".
"""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desafio_itau.settings")
import django  # noqa: E402

django.setup()

from django.test import Client  # noqa: E402

from apps.context_agent_datadriven.services import plano_proposta, usuario_real  # noqa: E402

UUIDS = ["00108ccd-699c-453a-a9f9-a66aad6e03e5", "001221d1-3626-45c1-807a-990502adf808"]
BASE = "/api/v1/context-agent/"
NUM = (int, float)

# campo -> tipo aceito, espelhando os tipos ApiProposal / ApiBalance do front
PROPOSTA = {
    "usuario.indice": int, "usuario.primeiro_anomes": int, "estado": str, "regra": str, "segmento_t3": str,
    "data_corte": str, "compromissos": list,
    **{f"totais.{k}": NUM for k in ("valor_liberado", "reserva", "falta_apos_cortes", "inflow_mensal",
                                     "surplus_mensal", "necessario_para_surplus_15")},
}
ITEM = {"subcategoria": str, "categoria_macro": str, "nivel": str, "gasto_atual": NUM, "corte": NUM,
        "meta": NUM, "texto": str, "lancamentos_na_janela": int}
SALDO = {"data_corte": str, "periodo.rotulo": str, "saldo": NUM, "negativado": bool,
         "media_mensal": dict, "negativado_na_media": (bool, str), "selo.fonte": str, "selo.medido_em": str}
ESTADOS = {"OK", "LIVRE_SEM_CORTE", "CORTE_INSUFICIENTE"}  # ProposalState em src/types/plan.ts


def _pegar(corpo, caminho):
    for parte in caminho.split("."):
        if not isinstance(corpo, dict) or parte not in corpo:
            return KeyError
        corpo = corpo[parte]
    return corpo


def faltas(corpo: dict, esquema: dict) -> list[str]:
    erros = []
    for caminho, tipo in esquema.items():
        valor = _pegar(corpo, caminho)
        if valor is KeyError:
            erros.append(f"falta {caminho}")
        elif isinstance(valor, bool) and bool not in (tipo if isinstance(tipo, tuple) else (tipo,)):
            erros.append(f"{caminho} é bool")
        elif not isinstance(valor, tipo):
            erros.append(f"{caminho} é {type(valor).__name__}")
    return erros


def faltas_proposta(corpo: dict) -> list[str]:
    erros = faltas(corpo, PROPOSTA)
    if corpo.get("estado") not in ESTADOS:
        erros.append(f"estado fora do front: {corpo.get('estado')}")
    for i, item in enumerate(corpo.get("compromissos") or []):
        erros += [f"compromissos[{i}].{e}" for e in faltas(item, ITEM)]
        if not str(item.get("nivel", "")).startswith(("Nível 1", "Nível 2")):
            erros.append(f"compromissos[{i}].nivel sem prefixo 'Nível 1/2': {item.get('nivel')}")
    return erros


class ExecutorFalso:
    def executar(self, sql, parametros):
        self.ultimo_job = {"job_id": "job-contrato", "bytes_processados": 10}
        if "ROW_NUMBER" in sql:
            return [{"indice": i + 1, "id_usuario": u, "movimentos": 400, "meses": 12,
                     "primeiro_anomes": 202501, "ultimo_anomes": 202512} for i, u in enumerate(UUIDS)]
        if "segmento_t3" in sql:
            return [{"meses": 11, "inflow_mensal": 10000.0, "outflow_mensal": 9000.0, "surplus_mensal": 1000.0,
                     "taxa_surplus_pct": 10.0, "saidas_sem_grupo": 0, "segmento_t3": "Esbanjador"}]
        return [{"lancamentos": 40, "entradas": 5000.0, "saidas": 5380.0}]


LINHAS = [{"macro": "Delivery", "subcategoria": "Delivery", "lancamentos": 30, "total": 11000.0,
           "gasto_mensal": 1000.0, "meses": 11, "base_inicio": 202501, "base_fim": 202511}]
SELO = {"fonte": "t", "medido_em": "m"}


class ContratoFrontMainTest(unittest.TestCase):
    def setUp(self):
        usuario_real.cache.limpar()
        for alvo, valor in ((usuario_real, ("_novo_executor", ExecutorFalso)),
                            (plano_proposta, ("subcategorias_discricionarias", lambda u, c: (LINHAS, SELO))),
                            (plano_proposta, ("gasto_ate_linha_de_corte", lambda u, c: ({}, SELO)))):
            p = patch.object(alvo, *valor)
            p.start()
            self.addCleanup(p.stop)
        self.client = Client()

    def test_proposta_tem_tudo_que_planApi_le(self):
        # igual ao front: só Content-Type, sem X-CSRFToken nem cookie
        r = self.client.post(BASE + "i-agora/plano/proposta/", {"ref": 1}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content[:300])
        corpo = r.json()
        self.assertEqual(faltas_proposta(corpo), [])
        self.assertEqual(corpo["usuario"]["indice"], 1)  # Maria (id 0 no front) -> ref 1
        self.assertEqual(len(corpo["data_corte"]), 10)   # front faz slice(0,10) e split('-')

    def test_saldo_mes_tem_tudo_que_balanceApi_le(self):
        r = self.client.get(BASE + "usuario-real/1/saldo-mes/")
        self.assertEqual(r.status_code, 200, r.content[:300])
        corpo = r.json()
        self.assertEqual(faltas(corpo, SALDO), [])
        self.assertEqual((corpo["saldo"], corpo["negativado"], corpo["negativado_na_media"]), (-380.0, True, False))

    # --- provas negativas ---
    def test_validador_acusa_campo_ausente_e_nivel_invalido(self):
        r = self.client.post(BASE + "i-agora/plano/proposta/", {"ref": 1}, content_type="application/json")
        corpo = r.json()
        del corpo["totais"]["valor_liberado"]
        corpo["compromissos"][0]["nivel"] = "Nível 3"
        erros = faltas_proposta(corpo)
        self.assertIn("falta totais.valor_liberado", erros)
        self.assertTrue(any("nivel sem prefixo" in e for e in erros))

    def test_bigquery_fora_responde_503_que_o_front_trata_como_nao_medido(self):
        class Quebrado:
            def executar(self, sql, parametros):
                raise ConnectionError("sem ADC")
        with patch.object(usuario_real, "_novo_executor", Quebrado):
            r = self.client.get(BASE + "usuario-real/1/saldo-mes/")
        self.assertEqual(r.status_code, 503)  # balanceApi: !res.ok -> saldoMedido = null


if __name__ == "__main__":
    unittest.main()
