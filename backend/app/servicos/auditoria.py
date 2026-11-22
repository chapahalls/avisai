"""Evidência única das decisões do agente para consumo do CCO."""
from typing import Any

from ..dominio.enums import TipoEvento


def decisao(
    c,
    rota_id: int,
    *,
    percebeu: str,
    decidiu: str,
    executou: str,
    resultado: str,
    prioridade: str = "info",
    **dados: Any,
) -> None:
    """Persiste as quatro fases; não há resultado implícito somente em logs."""
    estrutura = {
        "percebeu": percebeu,
        "decidiu": decidiu,
        "executou": executou,
        "resultado": resultado,
        "prioridade": prioridade,
    }
    c.eventos.registrar(
        TipoEvento.DECISAO_AGENTE,
        f"{decidiu}: {resultado}",
        rota_id,
        decisao=estrutura,
        prioridade=prioridade,
        _fonte="agent",
        **dados,
    )
