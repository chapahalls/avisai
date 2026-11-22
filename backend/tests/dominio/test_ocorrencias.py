"""Aprofundamento de ocorrências: cada tipo tem perguntas, feitas uma de cada vez."""
from app.dominio import ocorrencias as oc


def test_acidente_tem_roteiro_de_seguranca_primeiro():
    campos = [c for c, _ in oc.PERGUNTAS["acidente"]]
    assert campos[0] == "feridos"  # segurança vem antes de tudo
    assert {"envolvido", "consegue_seguir", "local"} <= set(campos)


def test_todos_os_tipos_tem_perguntas():
    for tipo in ("acidente", "avaria", "atraso", "fila", "doca_ocupada", "documento", "recusa", "outro"):
        assert oc.PERGUNTAS[tipo], tipo


def test_proxima_pergunta():
    assert "ferido" in oc.proxima("acidente", ["feridos", "envolvido"]).lower()
    assert oc.proxima("acidente", []) is None


def test_extrai_sim_nao():
    assert oc.extrair("feridos", "não, ninguém se machucou") == "não"
    assert oc.extrair("feridos", "sim, o motorista do carro tá ferido") == "sim"
    assert oc.extrair("consegue_seguir", "dá pra seguir sim") == "sim"
    assert oc.extrair("envolvido", "foi um carro na minha frente, não fui eu") == "foi um carro na minha frente, não fui eu"


def test_acidente_com_ferido_e_grave():
    assert oc.grave("acidente", {"feridos": "sim"})
    assert not oc.grave("acidente", {"feridos": "não"})
    assert oc.grave("acidente", {"envolvido": "o meu caminhão bateu", "feridos": "não"}) is False


def test_resumo_para_o_cco():
    r = oc.resumo("acidente", "acidente na pista", {"feridos": "não", "envolvido": "carro na frente", "consegue_seguir": "sim"})
    assert "acidente na pista" in r and "feridos: não" in r and "consegue seguir: sim" in r
