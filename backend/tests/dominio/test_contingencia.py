"""Diálogo sem LLM: entende a intenção e responde com o estado da rota (domínio puro)."""
import pytest

from app.dominio import contingencia as ct
from app.dominio.contingencia import Estado

VAZIO = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="em_transito")
PARADO = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="no_destino",
                tempo_parado="1 hora e 20 minutos", franquia_restante="3 horas e 40 minutos",
                valor="R$ 0,00", task_status="pendente", tentativas_cco=2)
RESPONDIDO = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="no_destino",
                    tempo_parado="6 horas", franquia_restante="0 minutos", valor="R$ 70,00",
                    task_status="escalada_recebedor", doca="4", previsao="em 40 minutos",
                    resumo_recebedor="A doca 4 libera em 40 minutos.")


@pytest.mark.parametrize("fala", ["Cheguei na portaria", "tô no pátio do cliente", "chegamos aqui no Mercadão", "estou na portaria"])
def test_chegada(fala):
    d = ct.decidir("motorista", fala, VAZIO)
    assert d.ferramenta == "confirmar_chegada"


@pytest.mark.parametrize("fala", ["Descarreguei", "já terminou a descarga", "liberaram o caminhão, tá vazio"])
def test_descarga(fala):
    assert ct.decidir("motorista", fala, PARADO).ferramenta == "confirmar_descarga"


@pytest.mark.parametrize("fala,tipo", [
    ("tem uma fila de três caminhões", "fila"),
    ("a doca tá ocupada", "doca_ocupada"),
    ("pediram outra nota fiscal", "documento"),
    ("furou um pneu", "avaria"),
    ("o recebedor recusou a carga", "recusa"),
    ("vou atrasar uns trinta minutos", "atraso"),
])
def test_ocorrencias(fala, tipo):
    d = ct.decidir("motorista", fala, PARADO)
    assert d.ferramenta == "registrar_ocorrencia" and d.args["tipo"] == tipo and d.args["descricao"] == fala


def test_pergunta_tempo_parado_responde_com_estado():
    d = ct.decidir("motorista", "quanto tempo eu tô parado?", PARADO)
    assert d.ferramenta is None
    assert "1 hora e 20 minutos" in d.texto and "3 horas e 40 minutos" in d.texto


def test_pergunta_estadia_valor():
    d = ct.decidir("motorista", "quanto já deu de estadia?", RESPONDIDO)
    assert "R$ 70,00" in d.texto


def test_pergunta_doca_com_resposta_do_recebedor():
    d = ct.decidir("motorista", "e aí, qual a doca?", RESPONDIDO)
    assert d.ferramenta is None and "doca 4" in d.texto and "40 minutos" in d.texto


def test_pergunta_doca_sem_resposta_ainda():
    d = ct.decidir("motorista", "alguma notícia da doca?", PARADO)
    assert d.ferramenta is None and "CCO" in d.texto


def test_pergunta_sobre_cco():
    d = ct.decidir("motorista", "o CCO respondeu?", PARADO)
    assert "2" in d.texto or "duas" in d.texto


def test_saudacao_resume_situacao():
    d = ct.decidir("motorista", "bom dia", PARADO)
    assert d.ferramenta is None and "Carlos" in d.texto and "parado" in d.texto


def test_nao_entendeu_explica_o_que_faz():
    d = ct.decidir("motorista", "o senhor é o editor que investigamos", VAZIO)
    assert d.ferramenta is None
    assert "chegada" in d.texto and "ocorrência" in d.texto


def test_acentos_e_maiusculas_nao_atrapalham():
    assert ct.decidir("motorista", "CHEGUEI NA PORTARIA", VAZIO).ferramenta == "confirmar_chegada"
    assert ct.decidir("motorista", "descarreguei já", PARADO).ferramenta == "confirmar_descarga"


@pytest.mark.parametrize("fala,doca,prev", [
    ("a doca 4 libera em 40 minutos", "4", "em 40 minutos"),
    ("pode mandar pra doca dois às 15h", "2", "às 15h"),
    ("daqui uma hora na doca 7", "7", "daqui uma hora"),
])
def test_recebedor_extrai_doca_e_previsao(fala, doca, prev):
    d = ct.decidir("recebedor", fala, PARADO)
    assert d.ferramenta == "registrar_resposta_recebedor"
    assert d.args["doca"] == doca and d.args["previsao"] == prev and d.args["resumo"] == fala


def test_recebedor_nao_recebe_hoje():
    d = ct.decidir("recebedor", "hoje não recebemos mais, só amanhã", PARADO)
    assert d.ferramenta == "registrar_resposta_recebedor" and "amanhã" in d.args["previsao"]


def test_recebedor_sem_resposta_agente_pergunta_de_novo():
    d = ct.decidir("recebedor", "alô? quem fala?", PARADO)
    assert d.ferramenta is None and "doca" in d.texto


# ---------- fluxos do repo de ideias ----------
NA_ORIGEM = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="na_origem", retirada_pendente=True)
INICIAL = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="em_transito",
                 inicial_faltantes=["estado_caminhao", "carga"])
CHECKIN = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="no_destino",
                 checkin_faltantes=["status_carga", "tempo_viagem", "problemas"])
CENTRAL = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="em_transito", pergunta_central="Qual o número do lacre?")


def test_confirma_retirada_na_origem():
    d = ct.decidir("motorista", "confirmo, peguei a carga", NA_ORIGEM)
    assert d.ferramenta == "confirmar_retirada" and "caminhão" in d.texto


def test_relatorio_inicial_extrai_campos():
    d = ct.decidir("motorista", "caminhão tá tudo certo, peguei 28 paletes", INICIAL)
    assert d.ferramenta == "registrar_relatorio_inicial"
    assert d.args["estado_caminhao"] and d.args["carga"]


def test_checkin_parcial_pergunta_so_o_que_falta():
    d = ct.decidir("motorista", "a carga tá inteira", CHECKIN)
    assert d.ferramenta == "registrar_checkin" and d.args == {"status_carga": "ok"}
    assert "tempo de viagem" in d.texto and "problema" in d.texto and "carga" not in d.texto.split("E ")[-1]


def test_checkin_completo_numa_frase():
    d = ct.decidir("motorista", "carga ok, foram três horas de viagem, sem problema", CHECKIN)
    assert d.args == {"status_carga": "ok", "tempo_viagem": "três horas", "problemas": "nenhum"}
    assert "completo" in d.texto


def test_resposta_para_a_central():
    d = ct.decidir("motorista", "o lacre é 4471", CENTRAL)
    assert d.ferramenta == "responder_central" and d.args["resposta"] == "o lacre é 4471"


def test_chegada_ja_pede_o_checkin():
    d = ct.decidir("motorista", "cheguei", VAZIO)
    assert "tempo de viagem" in d.texto
