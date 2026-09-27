"""guard_situacao com NAO_MEDIDO: a abstenção explícita do roteiro passa; afirmação continua reprovada.

Achado da sessão d9 em 2026-09-27 09:01: o texto NAO_MEDIDO de fluxos_comportamento.json era reprovado e a rota
devolvia 503 sem texto em vez do aviso honesto.
"""
import json
import unittest
from pathlib import Path

import conversas_apoio  # noqa: F401 -- configura o Django

from apps.conversas.interacao_avaliacao import NAO_MEDIDO, REPROVADO, guard_situacao

FLUXOS = Path(__file__).resolve().parents[1] / 'apps' / 'conversas' / 'fluxos_comportamento.json'


def textos_com(trecho, no=None):
    no = json.loads(FLUXOS.read_text(encoding='utf-8')) if no is None else no
    if isinstance(no, str):
        return [no] if trecho in no else []
    filhos = no.values() if isinstance(no, dict) else no if isinstance(no, list) else []
    return [t for f in filhos for t in textos_com(trecho, f)]


def reprovou(texto):
    return any(c['resultado'] == REPROVADO for c in guard_situacao(texto, NAO_MEDIDO, exige=True))


class AbstencaoComNaoMedido(unittest.TestCase):
    def test_textos_do_roteiro_passam(self):
        textos = textos_com('não vou afirmar')
        self.assertGreaterEqual(len(textos), 4)  # linhas 58, 118, 175, 222 no achado
        for t in textos:
            self.assertFalse(reprovou(t), t)

    def test_prova_negativa_afirmacoes_continuam_reprovadas(self):
        for t in ('Neste mês sobrou dinheiro.', 'Faltou R$ 200 no mês.', 'Não sobrou nada este mês.',
                  'Não vou mentir: faltou dinheiro.'):
            self.assertTrue(reprovou(t), t)


if __name__ == '__main__':
    unittest.main()
