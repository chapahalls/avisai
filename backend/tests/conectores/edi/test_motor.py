"""Motor de EDI de largura fixa: formatação, leitura e as regras que protegem contra erro de digitação."""
import pytest

from app.conectores.edi.motor import Campo, ErroEdi, Registro, formatar, formatar_campo, ler, validar_layout

REGISTRO = Registro(id="999", tamanho=10, campos=(
    Campo(nome="id", pos=1, tamanho=3, tipo="N", status="M"),
    Campo(nome="nome", pos=4, tamanho=5, tipo="A", status="M"),
    Campo(nome="obs", pos=9, tamanho=2, tipo="A", status="C"),
))


def test_formata_alinhando_n_a_direita_e_a_a_esquerda():
    linha = formatar(REGISTRO, {"id": "7", "nome": "Ana", "obs": "x"})
    assert linha == "007Ana  x "
    assert len(linha) == 10


def test_campo_a_maiuscula():
    campo = Campo(nome="nome", pos=1, tamanho=5, tipo="A", status="M", maiuscula=True)
    assert formatar_campo(campo, "ana") == "ANA  "


def test_campo_n_com_decimais_implicitos():
    campo = Campo(nome="valor", pos=1, tamanho=6, tipo="N", decimais=2, status="M")
    assert formatar_campo(campo, "12.5") == "001250"


def test_campo_m_vazio_e_erro():
    with pytest.raises(ErroEdi, match="obrigatório"):
        formatar(REGISTRO, {"id": "7", "nome": None, "obs": None})


def test_campo_c_vazio_zero_ou_espaco_fill():
    linha = formatar(REGISTRO, {"id": "7", "nome": "Ana", "obs": None})
    assert linha == "007Ana    "


def test_valor_maior_que_o_campo_e_erro_nunca_truncamento():
    with pytest.raises(ErroEdi, match="não cabe"):
        formatar(REGISTRO, {"id": "7", "nome": "Fernanda", "obs": None})
    with pytest.raises(ErroEdi, match="não cabe"):
        formatar(REGISTRO, {"id": "123456", "nome": "Ana", "obs": None})


def test_tamanho_do_registro_formatado_bate_com_a_especificacao():
    linha = formatar(REGISTRO, {"id": "7", "nome": "Ana", "obs": None})
    assert len(linha) == REGISTRO.tamanho


def test_ler_e_o_inverso_de_formatar():
    linha = formatar(REGISTRO, {"id": "7", "nome": "Ana", "obs": "x"})
    valores = ler(linha, REGISTRO)
    assert valores["id"] == 7
    assert valores["nome"] == "Ana"
    assert valores["obs"] == "x"


def test_ler_campo_c_vazio_devolve_none():
    linha = formatar(REGISTRO, {"id": "7", "nome": "Ana", "obs": None})
    valores = ler(linha, REGISTRO)
    assert valores["obs"] is None


def test_ler_campo_n_zero_filled_tambem_e_vazio():
    """"Campo vazio: zeros se N" (regra do motor) -- um C numérico ausente lê como None, não como 0."""
    registro_n = Registro(id="998", tamanho=5, campos=(
        Campo(nome="data", pos=1, tamanho=5, tipo="N", status="C"),
    ))
    linha = formatar(registro_n, {"data": None})
    assert ler(linha, registro_n)["data"] is None


def test_ler_linha_com_tamanho_errado_e_erro():
    with pytest.raises(ErroEdi, match="posições"):
        ler("curta", REGISTRO)


def test_validar_layout_aceita_registro_sem_buraco_nem_sobreposicao():
    validar_layout(REGISTRO)  # não levanta


def test_validar_layout_rejeita_buraco():
    com_buraco = Registro(id="999", tamanho=10, campos=(
        Campo(nome="id", pos=1, tamanho=3, tipo="N", status="M"),
        Campo(nome="nome", pos=5, tamanho=5, tipo="A", status="M"),  # devia começar em 4
    ))
    with pytest.raises(ErroEdi, match="esperava 4"):
        validar_layout(com_buraco)


def test_validar_layout_rejeita_soma_diferente_do_tamanho():
    maior = Registro(id="999", tamanho=10, campos=(
        Campo(nome="id", pos=1, tamanho=3, tipo="N", status="M"),
        Campo(nome="nome", pos=4, tamanho=5, tipo="A", status="M"),
        Campo(nome="obs", pos=9, tamanho=5, tipo="A", status="C"),  # ultrapassa o tamanho do registro
    ))
    with pytest.raises(ErroEdi, match="somam"):
        validar_layout(maior)


def test_campo_com_tipo_ou_status_invalido_e_erro():
    with pytest.raises(ValueError, match="tipo"):
        Campo(nome="x", pos=1, tamanho=1, tipo="X", status="M")
    with pytest.raises(ValueError, match="status"):
        Campo(nome="x", pos=1, tamanho=1, tipo="A", status="X")
