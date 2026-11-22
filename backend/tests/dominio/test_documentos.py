"""Pergunta sobre a NF/CT-e por voz: responde só com campos do documento, cita a fonte, ou "não encontrei"."""
from types import SimpleNamespace

import pytest

from app.dominio import documentos

ROTA = SimpleNamespace(id=1, placa="RST-4B21", nota_fiscal="000.482.913", carga_t=28,
                       carga_descricao="28 paletes de bebidas", recebedor_empresa="Mercadão Campinas")
DOCS = documentos.da_rota(ROTA, "Transportadora Rota Sul")


def test_documentos_da_rota_tem_nfe_e_cte():
    tipos = {d["kind"] for d in DOCS}
    assert tipos == {"NF-e", "CT-e"}
    nfe = next(d for d in DOCS if d["kind"] == "NF-e")
    assert nfe["campos"]["numero"] == "000.482.913" and nfe["campos"]["peso_kg"] == 28000


@pytest.mark.parametrize("pergunta,campo,trecho", [
    ("qual o número da nota?", "numero", "000.482.913"),
    ("qual o peso da NF?", "peso_kg", "28.000 kg"),
    ("quanto vale a carga na nota fiscal?", "valor", "R$ 84.230,50"),
    ("pra quem é a nota?", "destinatario", "Mercadão Campinas"),
    ("o que tem na nota?", "itens", "28 paletes de bebidas"),
    ("qual o número do CT-e?", "numero", "000.771.204"),
    ("qual o valor do frete?", "frete", "R$ 3.120,00"),
])
def test_consulta_responde_com_campo_e_cita_documento(pergunta, campo, trecho):
    r = documentos.consultar(DOCS, pergunta)
    assert r["encontrado"] and r["campo"] == campo
    assert trecho in r["resposta"]
    assert r["documento"] in r["resposta"]  # cita qual documento usou


def test_pergunta_sem_campo_diz_nao_encontrei():
    r = documentos.consultar(DOCS, "qual a cor do caminhão?")
    assert not r["encontrado"] and "não encontrei" in r["resposta"].lower()


def test_cte_explicito_nao_cai_na_nfe():
    r = documentos.consultar(DOCS, "qual o número do conhecimento de transporte?")
    assert r["documento"].startswith("CT-e")


def test_eh_pergunta_de_documento():
    assert documentos.eh_pergunta("qual o peso da nota?")
    assert documentos.eh_pergunta("me fala o número do CT-e")
    assert not documentos.eh_pergunta("cheguei na portaria")
