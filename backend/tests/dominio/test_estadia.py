"""Estadia: Lei 11.442 (franquia 5h) e R$ 2,50 por t/h (ANTT, abr/2026). Domínio puro."""
from datetime import datetime, timedelta

from app.dominio import estadia

T0 = datetime(2026, 11, 22, 10, 0)


def test_quatro_horas_parado_ainda_na_franquia():
    x = estadia.calcular(inicio=T0, agora=T0 + timedelta(hours=4), capacidade_t=28)
    assert x.valor == 0
    assert x.franquia_restante_h == 1
    assert x.tempo_parado == "4h00"


def test_sete_horas_parado_cobra_duas_horas_excedentes():
    x = estadia.calcular(inicio=T0, agora=T0 + timedelta(hours=7), capacidade_t=28)
    assert x.horas_excedentes == 2
    assert x.valor == 140.0
    assert x.valor_fmt == "R$ 140,00"
    assert x.franquia_restante_h == 0


def test_aceleracao_da_demo():
    x = estadia.calcular(inicio=T0, agora=T0 + timedelta(seconds=6), capacidade_t=28, aceleracao=600)
    assert x.horas_paradas == 1


def test_estadia_encerrada_congela():
    fim = T0 + timedelta(hours=6)
    x = estadia.calcular(inicio=T0, agora=T0 + timedelta(hours=20), fim=fim, capacidade_t=10)
    assert x.horas_paradas == 6
    assert x.valor == 25.0
    assert x.encerrada


def test_falar_horas_em_portugues():
    assert estadia.falar_horas(1.5) == "1 hora e 30 minutos"
    assert estadia.falar_horas(0.0) == "0 minutos"
    assert estadia.falar_horas(2) == "2 horas"
