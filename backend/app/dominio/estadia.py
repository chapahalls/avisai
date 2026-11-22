"""Cálculo da estadia (Lei 11.442/2007, art. 11): franquia de 5h e valor por tonelada/hora."""
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Resumo:
    inicio: datetime
    fim: Optional[datetime]
    encerrada: bool
    horas_paradas: float
    tempo_parado: str
    franquia_h: float
    franquia_restante_h: float
    franquia_restante: str
    horas_excedentes: float
    capacidade_t: float
    valor_t_h: float
    valor: float
    valor_fmt: str

    def dict(self) -> dict:
        return asdict(self)


def calcular(
    *,
    inicio: datetime,
    agora: datetime,
    capacidade_t: float,
    fim: Optional[datetime] = None,
    franquia_h: float = 5,
    valor_t_h: float = 2.50,
    aceleracao: float = 1,
) -> Resumo:
    ate = fim or agora
    h = max(0.0, (ate - inicio).total_seconds()) * aceleracao / 3600
    excedente = max(0.0, h - franquia_h)
    valor = round(excedente * capacidade_t * valor_t_h, 2)
    restante = max(0.0, franquia_h - h)
    return Resumo(
        inicio=inicio,
        fim=fim,
        encerrada=fim is not None,
        horas_paradas=round(h, 4),
        tempo_parado=formatar_horas(h),
        franquia_h=franquia_h,
        franquia_restante_h=round(restante, 4),
        franquia_restante=formatar_horas(restante),
        horas_excedentes=round(excedente, 4),
        capacidade_t=capacidade_t,
        valor_t_h=valor_t_h,
        valor=valor,
        valor_fmt=formatar_reais(valor),
    )


def formatar_horas(h: float) -> str:
    m = int(math.floor(h * 60 + 1e-9))
    return f"{m // 60}h{m % 60:02d}"


def formatar_reais(v: float) -> str:
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def falar_horas(h: float) -> str:
    m = int(math.floor(h * 60 + 1e-9))
    horas, minutos = divmod(m, 60)
    partes = []
    if horas:
        partes.append(f"{horas} hora" + ("s" if horas > 1 else ""))
    if minutos or not partes:
        partes.append(f"{minutos} minuto" + ("s" if minutos != 1 else ""))
    return " e ".join(partes)
