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


def test_fila_na_estrada_e_corrigida_para_atraso():
    """Não existe fila de caminhões num recebedor enquanto o caminhão ainda está na pista."""
    assert oc.corrigir_tipo_por_estado("fila", "em_transito") == "atraso"


def test_fila_fora_da_estrada_nao_e_alterada():
    for status in ("planejada", "na_origem", "aproximando", "no_destino", "descarregada"):
        assert oc.corrigir_tipo_por_estado("fila", status) == "fila", status


def test_outros_tipos_nunca_sao_alterados():
    for tipo in ("atraso", "avaria", "acidente", "doca_ocupada", "documento", "recusa", "outro"):
        assert oc.corrigir_tipo_por_estado(tipo, "em_transito") == tipo


# ---------- 5e/5e2: fila na doca depois da chegada não é o atraso aberto na estrada ----------

def test_indica_fila_na_doca():
    assert oc.indica_fila_na_doca("Tem uma fila de caminhões aqui na portaria")
    assert oc.indica_fila_na_doca("Uns cinco caminhões na frente")
    assert not oc.indica_fila_na_doca("Vou atrasar uns 40 minutos, trânsito parado")


def test_deve_abrir_fila_separada_so_depois_da_chegada_com_atraso_aberto():
    assert oc.deve_abrir_fila_separada("atraso", "no_destino", "Tem uma fila de caminhões aqui")
    assert not oc.deve_abrir_fila_separada("atraso", "em_transito", "Tem uma fila de caminhões aqui")
    assert not oc.deve_abrir_fila_separada("fila", "no_destino", "Tem uma fila de caminhões aqui")
    assert not oc.deve_abrir_fila_separada("atraso", "no_destino", "Vou atrasar mais uns minutos")
