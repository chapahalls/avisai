"""Geocercas e política de escalonamento (domínio puro)."""
from app.dominio import escalonamento, geocerca

DEST = (-22.9056, -47.0608)


def test_longe_nao_dispara_nada():
    x = geocerca.avaliar(-23.1857, -46.8978, DEST, 60, aproximacao_min=15, raio_chegada_m=300)
    assert x.distancia_m > 25000 and not x.aproximou and not x.chegou


def test_eta_dentro_da_janela_de_aproximacao():
    x = geocerca.avaliar(-22.9956, -47.0608, DEST, 60, aproximacao_min=15, raio_chegada_m=300)
    assert 9000 < x.distancia_m < 11000
    assert x.eta_min <= 15 and x.aproximou and not x.chegou


def test_dentro_do_raio_e_chegada():
    x = geocerca.avaliar(-22.9057, -47.0609, DEST, 60, aproximacao_min=15, raio_chegada_m=300)
    assert x.chegou and not x.aproximou


def test_canal_e_prioridade_sobem_a_cada_tentativa():
    niveis = ["push", "painel", "ligacao"]
    assert escalonamento.nivel(1, niveis) == ("push", "normal")
    assert escalonamento.nivel(2, niveis) == ("painel", "alta")
    assert escalonamento.nivel(3, niveis) == ("ligacao", "critica")
    assert escalonamento.nivel(5, niveis) == ("ligacao", "critica")
