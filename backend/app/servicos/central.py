"""Pedido da central: o CCO pergunta, o agente repassa ao motorista e a resposta volta estruturada."""
from typing import Optional

from sqlmodel import select

from ..dominio.enums import TipoEvento
from ..infra.db import sessao
from ..infra.models import SolicitacaoCentral
from . import consultas
from .sessoes import VozAgora


def pendente(rota_id: int) -> Optional[SolicitacaoCentral]:
    with sessao() as s:
        return s.exec(select(SolicitacaoCentral).where(SolicitacaoCentral.rota_id == rota_id,
                                                       SolicitacaoCentral.status == "perguntada")
                      .order_by(SolicitacaoCentral.id.desc())).first()


async def perguntar(c, rota_id: int, pergunta: str) -> SolicitacaoCentral:
    consultas.rota(rota_id)
    with sessao() as s:
        sol = SolicitacaoCentral(rota_id=rota_id, pergunta=pergunta, status="perguntada", criada_em=c.relogio.agora())
        s.add(sol)
        s.commit()
        s.refresh(sol)
    c.eventos.registrar(TipoEvento.PEDIDO_CENTRAL, f"Central pergunta: {pergunta}", rota_id, solicitacao_id=sol.id)
    await VozAgora(c).falar_motorista(rota_id, f"A central pergunta: {pergunta}")
    return sol


def responder(c, rota_id: int, resposta: str, transcricao: Optional[str] = None) -> Optional[SolicitacaoCentral]:
    sol = pendente(rota_id)
    if not sol:
        return None
    with sessao() as s:
        sol = s.get(SolicitacaoCentral, sol.id)
        sol.resposta, sol.status, sol.respondida_em, sol.transcricao = resposta, "respondida", c.relogio.agora(), transcricao
        s.add(sol)
        s.commit()
        s.refresh(sol)
    c.eventos.registrar(TipoEvento.RESPOSTA_CENTRAL, f"Motorista respondeu à central: {resposta}", rota_id,
                        solicitacao_id=sol.id, pergunta=sol.pergunta, resposta=resposta)
    return sol


def listar(rota_id: int) -> list[SolicitacaoCentral]:
    with sessao() as s:
        return s.exec(select(SolicitacaoCentral).where(SolicitacaoCentral.rota_id == rota_id)
                      .order_by(SolicitacaoCentral.id.desc())).all()
