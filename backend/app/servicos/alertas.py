"""Classificação determinística das falas do motorista para alertas da CCO."""
import re
from dataclasses import dataclass

from ..dominio.enums import TipoEvento
from . import auditoria


@dataclass(frozen=True)
class Alerta:
    tipo: str
    resumo: str
    prioridade: str


def classificar(fala: str) -> Alerta:
    texto = fala.strip()
    normalizado = texto.lower()
    if re.search(r"\b(descarreg|descarga|liberar|terminou)\b", normalizado):
        return Alerta("descarga", "Motorista informou descarga ou liberação.", "info")
    if re.search(r"\b(pneu|furou|acidente|avaria|problema|quebrou|pane|socorro)\b", normalizado):
        return Alerta("problema", "Motorista relatou um problema na rota.", "critico")
    if re.search(r"\b(atras|demora|vou chegar.*hora|mais\s+\d+\s*(h|hora|min))", normalizado):
        return Alerta("atraso", "Motorista informou atraso na viagem.", "critico")
    if re.search(r"\b(cheguei|chegamos|portaria|p[aá]tio|destino)\b", normalizado):
        return Alerta("chegada", "Motorista informou chegada ao destino.", "atencao")
    if re.search(r"\b(aproxim|perto|faltam|chegando)\b", normalizado):
        return Alerta("aproximacao", "Motorista informou aproximação ao destino.", "info")
    # A fala ainda é visível e auditável; sem inventar um problema ou atraso.
    return Alerta("aproximacao", "Atualização de viagem recebida do motorista.", "info")


def registrar(c, rota_id: int, fala: str) -> Alerta:
    alerta = classificar(fala)
    c.eventos.registrar(
        TipoEvento.ALERTA_MOTORISTA,
        alerta.resumo,
        rota_id,
        tipo=alerta.tipo,
        resumo=alerta.resumo,
        transcricao=fala,
        prioridade=alerta.prioridade,
        timestamp=c.relogio.agora().isoformat() + "Z",
        _fonte="driver",
    )
    if alerta.prioridade == "critico":
        auditoria.decisao(
            c,
            rota_id,
            percebeu=fala,
            decidiu=f"Classificar a fala como {alerta.tipo} crítico e avisar o CCO.",
            executou="Publicou alerta crítico em tempo real.",
            resultado="Aguardando ação do CCO.",
            prioridade="critico",
            alerta_tipo=alerta.tipo,
        )
    return alerta
