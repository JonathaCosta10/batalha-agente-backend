"""Base de calibragem de comportamento (desafio_itau/politica/comportamento-v1.json), offline, sem modelo.

Schema e provas negativas rodam sempre (casos sintéticos). Os testes sobre a base real pulam com NAO_MEDIDO enquanto
scripts/importar_comportamento.py não tiver gravado o arquivo: ausência não vira verde nem vira zero.
"""
import copy
import unittest

import conversas_apoio  # noqa: F401 -- configura o Django como os demais testes

from desafio_itau.politica import comportamento as cb
from desafio_itau.politica.comportamento import extrair_casos

CASO = {
    'id': 1, 'bloco': 'Diagnóstico e Jornada',
    'diagnostico_financeiro': {'perfil': 'Vulnerável', 'evidencias': ['saídas acima das entradas'], 'severidade': 'alta'},
    'tom_calibrado': 'acolhimento sereno', 'perfil_cliente': 'assalariado',
    'contexto_financeiro': {'renda_media': 3000, 'taxa_sobra': -0.05, 'consumo_flexivel': 0.2,
                            'volatilidade_recebimentos': 'baixa', 'sazonalidade': 'nenhuma', 'reserva': 0},
    'intencao_usuario': 'entender saldo', 'entrada_usuario': 'Por que meu dinheiro acaba antes do fim do mês?',
    'raciocinio_de_abordagem': 'mostrar entradas e saídas', 'resposta_ideal_iagora': 'Vamos olhar juntos o dinheiro do mês.',
    'acao_sugerida': 'organizar compromissos', 'gatilho_produto': 'Nenhum', 'compliance_check': 'ok',
}


def _base(casos):
    return {'schema_version': '1.0', 'id': 'comportamento-i-agora', 'versao': '1.0.0', 'natureza': 'dado_de_calibragem',
            'status': 'NAO_HOMOLOGADO',
            'fonte': {'descricao': 'sintetico', 'arquivo': 'teste', 'sha256': '0' * 64, 'lido_em': '2026-09-27 10:00 BRT'},
            'historico': ['1.0.0 teste'], 'achados': [], 'casos': casos}


class Schema(unittest.TestCase):
    def test_caso_sintetico_valido_passa(self):
        cb.validar(_base([CASO]))

    def test_prova_negativa_sem_contexto_financeiro_reprova(self):
        ruim = copy.deepcopy(CASO); del ruim['contexto_financeiro']
        with self.assertRaises(ValueError):
            cb.validar(_base([ruim]))

    def test_prova_negativa_taxa_sobra_maior_que_1_reprova(self):
        ruim = copy.deepcopy(CASO); ruim['contexto_financeiro']['taxa_sobra'] = 15
        with self.assertRaises(ValueError):
            cb.validar(_base([ruim]))

    def test_prova_negativa_campo_desconhecido_reprova(self):
        ruim = copy.deepcopy(CASO); ruim['inventado'] = 1
        with self.assertRaises(ValueError):
            cb.validar(_base([ruim]))

    def test_prova_negativa_id_repetido_reprova(self):
        with self.assertRaises(ValueError):
            cb.validar(_base([CASO, copy.deepcopy(CASO)]))


class Auditoria(unittest.TestCase):
    """O auditor TEM de apontar cada defeito sintético; e não aponta nada num caso limpo."""

    def test_caso_limpo_sem_alerta(self):
        _, alertas = cb.auditar([CASO])
        self.assertEqual(alertas, {})

    def test_aponta_defeitos_sinteticos(self):
        dup = copy.deepcopy(CASO); dup['id'] = 2
        vol = copy.deepcopy(CASO); vol['id'] = 3; vol['entrada_usuario'] = 'Comprar celular em 12x?'
        vol['diagnostico_financeiro']['perfil'] = ['Volatilidade de Recebimentos', 'Livre']
        proj = copy.deepcopy(CASO); proj['id'] = 4; proj['entrada_usuario'] = 'Consigo guardar R$ 150 por mês?'
        proj['resposta_ideal_iagora'] = 'Guardando R$ 200 por mês, você chega a R$ 1.100 em 6 meses. Rendimento garantido.'
        proj['gatilho_produto'] = 'Consórcio'
        itau = copy.deepcopy(CASO); itau['id'] = 5; itau['entrada_usuario'] = 'Como ganho pontos no programa?'
        itau['resposta_ideal_iagora'] = 'No Itaú você junta pontos.'
        achados, alertas = cb.auditar([CASO, dup, vol, proj, itau])
        por = {a['tipo']: a for a in achados}
        self.assertEqual(por['duplicados']['exatos'], [[1, 2]])
        self.assertTrue(any('perfil_multiplo' in x for x in alertas[3]))
        self.assertIn('perfil_volatilidade_com_volatilidade_baixa', alertas[3])
        self.assertTrue(any(x.startswith('perfil_livre_com_sobra') for x in alertas[3]))
        self.assertIn(3, por['resposta_ignora_pergunta_heuristica']['ids'])
        self.assertEqual(por['projecoes']['erradas'], [4])
        self.assertEqual(por['projecoes']['valor_fora_dos_dados'], [4])
        self.assertEqual(por['gatilho_produto']['ids'], [4])
        self.assertIn(4, por['lexico']['ids'])
        self.assertEqual(por['marca']['ids'], [5])

    def test_projecao_certa_nao_alerta(self):
        ok = copy.deepcopy(CASO); ok['entrada_usuario'] = 'Se eu guardar R$ 150 por mês?'
        ok['resposta_ideal_iagora'] = 'Guardando R$ 150 por mês, o dinheiro do mês vira R$ 900 em 6 meses.'
        achados, _ = cb.auditar([ok])
        proj = next(a for a in achados if a['tipo'] == 'projecoes')
        self.assertEqual((proj['contagem'], proj['erradas'], proj['valor_fora_dos_dados']), (1, [], []))

    def test_extrator_acha_array_no_meio_de_prosa(self):
        self.assertEqual([c['id'] for c in extrair_casos('texto antes [1, 2] ' + '[{"id": 7}, {"id": 8}] fim')], [7, 8])


@unittest.skipUnless(cb.ARQUIVO.exists(), 'NAO_MEDIDO: comportamento-v1.json ainda não importado '
                                         '(scripts/importar_comportamento.py <fonte>)')
class BaseReal(unittest.TestCase):
    def test_cem_casos_ids_unicos_1_a_100(self):
        base = cb.carregar()
        self.assertEqual([c.id for c in base.casos], list(range(1, 101)))

    def test_status_e_fonte(self):
        base = cb.carregar()
        self.assertEqual(base.status, 'NAO_HOMOLOGADO')
        self.assertIn('nao homologado', base.fonte.descricao)
        self.assertTrue(base.achados)


if __name__ == '__main__':
    unittest.main()
