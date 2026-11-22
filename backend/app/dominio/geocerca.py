"""Geocercas de aproximação (ETA) e chegada (raio). Domínio puro."""
import math
from dataclasses import dataclass


def distancia_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class Leitura:
    distancia_m: float
    eta_min: float
    aproximou: bool
    chegou: bool


def avaliar(lat: float, lng: float, destino: tuple[float, float], velocidade_kmh: float,
            aproximacao_min: float, raio_chegada_m: float) -> Leitura:
    d = distancia_m(lat, lng, *destino)
    eta = (d / 1000) / max(velocidade_kmh, 1) * 60
    chegou = d <= raio_chegada_m
    return Leitura(distancia_m=round(d), eta_min=round(eta, 1), aproximou=eta <= aproximacao_min and not chegou, chegou=chegou)
