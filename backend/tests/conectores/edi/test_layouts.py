"""Os layouts são dados, não código: o teste mais barato é confirmar que cobrem o registro sem buraco
nem sobreposição (o erro mais provável ao transcrever um manual de EDI em `Campo`/`Registro`)."""
import pytest

from app.conectores.edi.layouts import ocoren_31, ocoren_50
from app.conectores.edi.motor import validar_layout

LAYOUTS = (ocoren_50, ocoren_31)


@pytest.mark.parametrize("camada", LAYOUTS, ids=[c.NOME for c in LAYOUTS])
def test_todos_os_registros_cobrem_o_tamanho_sem_buraco_nem_sobreposicao(camada):
    for registro in camada.REGISTROS.values():
        validar_layout(registro)


@pytest.mark.parametrize("camada", LAYOUTS, ids=[c.NOME for c in LAYOUTS])
def test_todo_registro_tem_o_tamanho_fixo_do_layout(camada):
    for registro in camada.REGISTROS.values():
        assert registro.tamanho == camada.TAMANHO_REGISTRO


def test_ocoren_50_tem_registros_000_540_541_542():
    assert set(ocoren_50.REGISTROS) == {"000", "540", "541", "542"}


def test_ocoren_31_tem_registros_000_340_341_342():
    assert set(ocoren_31.REGISTROS) == {"000", "340", "341", "342"}


def test_so_o_542_da_5_0_tem_os_campos_da_prova_de_estadia():
    campos_542 = {campo.nome for campo in ocoren_50.REGISTRO_542.campos}
    for campo in ("chegada_destino_data", "inicio_descarga_data", "termino_descarga_data", "saida_destino_data"):
        assert campo in campos_542
    campos_342 = {campo.nome for campo in ocoren_31.REGISTRO_342.campos}
    assert "texto_livre" in campos_342
    assert not ({"chegada_destino_data", "termino_descarga_data"} & campos_342)


def test_3_1_exige_maiuscula_nos_campos_a_e_5_0_nao():
    assert any(campo.maiuscula for campo in ocoren_31.REGISTRO_000.campos if campo.tipo == "A")
    assert not any(campo.maiuscula for campo in ocoren_50.REGISTRO_000.campos if campo.tipo == "A")
