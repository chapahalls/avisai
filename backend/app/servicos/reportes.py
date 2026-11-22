"""Relatório inicial e check-in por voz, com validação de completude (o agente pergunta só o que faltou)."""
from typing import Optional

from sqlmodel import select

from ..dominio.enums import TipoEvento
from ..infra.db import sessao
from ..infra.models import Reporte

CAMPOS = {
    "inicial": ["estado_caminhao", "carga"],
    "checkin": ["status_carga", "tempo_viagem", "problemas"],
}
ROTULOS = {
    "estado_caminhao": "como está o caminhão",
    "carga": "a carga coletada",
    "status_carga": "como está a carga",
    "tempo_viagem": "quanto tempo de viagem",
    "problemas": "se teve algum problema",
}


def aberto(rota_id: int, tipo: str) -> Optional[Reporte]:
    with sessao() as s:
        return s.exec(select(Reporte).where(Reporte.rota_id == rota_id, Reporte.tipo == tipo, Reporte.completo == False)  # noqa: E712
                      .order_by(Reporte.id.desc())).first()


def faltantes_abertos(rota_id: int, tipo: str) -> Optional[list[str]]:
    """Campos que faltam no relatório em aberto; None se não há relatório em aberto."""
    r = aberto(rota_id, tipo)
    return list(r.faltantes) if r else None


def iniciar(c, rota_id: int, tipo: str) -> Reporte:
    """Abre um relatório vazio (ex.: check-in logo após a chegada)."""
    r = aberto(rota_id, tipo)
    if r:
        return r
    with sessao() as s:
        r = Reporte(rota_id=rota_id, tipo=tipo, faltantes=list(CAMPOS[tipo]), criado_em=c.relogio.agora())
        s.add(r)
        s.commit()
        s.refresh(r)
        return r


def registrar(c, rota_id: int, tipo: str, campos: dict, fala: Optional[str] = None) -> dict:
    validos = {k: str(v).strip() for k, v in (campos or {}).items() if k in CAMPOS[tipo] and v not in (None, "")}
    with sessao() as s:
        r = s.exec(select(Reporte).where(Reporte.rota_id == rota_id, Reporte.tipo == tipo, Reporte.completo == False)  # noqa: E712
                   .order_by(Reporte.id.desc())).first()
        if r and r.campos:
            r.perguntas_complemento += 1  # já tinha resposta parcial: esta é uma complementação
        if not r:
            r = Reporte(rota_id=rota_id, tipo=tipo, criado_em=c.relogio.agora())
        r.campos = {**(r.campos or {}), **validos}
        r.faltantes = [k for k in CAMPOS[tipo] if k not in r.campos]
        r.transcricao = list(r.transcricao or []) + ([fala] if fala else [])
        r.completo = not r.faltantes
        if r.completo:
            r.completo_em = c.relogio.agora()
        s.add(r)
        s.commit()
        s.refresh(r)
    nome = "relatório inicial" if tipo == "inicial" else "check-in"
    if r.completo:
        c.eventos.registrar(TipoEvento.RELATORIO, f"{nome.capitalize()} completo: " + "; ".join(f"{k}: {v}" for k, v in r.campos.items()),
                            rota_id, reporte_id=r.id, tipo_reporte=tipo, campos=r.campos,
                            perguntas_complemento=r.perguntas_complemento)
        return {"ok": True, "completo": True, "campos": r.campos}
    c.eventos.registrar(TipoEvento.CAMPO_FALTANTE, f"{nome.capitalize()} incompleto: falta " + ", ".join(r.faltantes), rota_id,
                        reporte_id=r.id, tipo_reporte=tipo, faltantes=r.faltantes)
    return {"ok": True, "completo": False, "faltando": r.faltantes,
            "pergunte_so_isto": " e ".join(ROTULOS[k] for k in r.faltantes)}
