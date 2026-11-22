"""Política de escalonamento do CCO: canal e prioridade sobem a cada tentativa. Domínio puro."""
from .enums import Prioridade

PRIORIDADES = [Prioridade.NORMAL, Prioridade.ALTA, Prioridade.CRITICA]


def nivel(tentativa: int, niveis: list[str]) -> tuple[str, str]:
    """tentativa começa em 1. Devolve (canal, prioridade)."""
    i = max(0, tentativa - 1)
    return niveis[min(i, len(niveis) - 1)], str(PRIORIDADES[min(i, len(PRIORIDADES) - 1)])
