"""Leituras compartilhadas pelos serviços."""
from typing import Optional

from sqlmodel import select

from ..dominio import estadia as est
from ..infra.db import sessao
from ..infra.models import Empresa, Estadia, LigacaoRecebedor, Motorista, Rota, SessaoAgente, TaskCCO


class NaoEncontrado(LookupError):
    pass


def rota(rota_id: int) -> Rota:
    with sessao() as s:
        r = s.get(Rota, rota_id)
    if not r:
        raise NaoEncontrado(f"rota {rota_id} não existe")
    return r


def contexto_rota(rota_id: int) -> tuple[Rota, str, str]:
    """(rota, nome do motorista, nome da empresa)."""
    with sessao() as s:
        r = s.get(Rota, rota_id)
        if not r:
            raise NaoEncontrado(f"rota {rota_id} não existe")
        m = s.get(Motorista, r.motorista_id) if r.motorista_id else None
        e = s.get(Empresa, r.empresa_id)
    return r, (m.nome if m else "parceiro"), (e.nome if e else "transportadora")


def estadia_aberta(rota_id: int) -> Optional[Estadia]:
    with sessao() as s:
        return s.exec(select(Estadia).where(Estadia.rota_id == rota_id, Estadia.fim == None)).first()  # noqa: E711


def ultima_estadia(rota_id: int) -> Optional[Estadia]:
    with sessao() as s:
        return s.exec(select(Estadia).where(Estadia.rota_id == rota_id).order_by(Estadia.id.desc())).first()


def ultima_task(rota_id: int) -> Optional[TaskCCO]:
    with sessao() as s:
        return s.exec(select(TaskCCO).where(TaskCCO.rota_id == rota_id).order_by(TaskCCO.id.desc())).first()


def ultima_ligacao(rota_id: int) -> Optional[LigacaoRecebedor]:
    with sessao() as s:
        return s.exec(
            select(LigacaoRecebedor).where(LigacaoRecebedor.rota_id == rota_id).order_by(LigacaoRecebedor.id.desc())
        ).first()


def sessao_ativa_motorista(rota_id: int) -> Optional[SessaoAgente]:
    with sessao() as s:
        return s.exec(
            select(SessaoAgente)
            .where(SessaoAgente.rota_id == rota_id, SessaoAgente.papel == "motorista", SessaoAgente.status == "ativa")
            .order_by(SessaoAgente.id.desc())
        ).first()


def resumo_estadia(c, e: Estadia) -> est.Resumo:
    return est.calcular(
        inicio=e.inicio, agora=c.relogio.agora(), fim=e.fim, capacidade_t=e.capacidade_t,
        franquia_h=e.franquia_h, valor_t_h=e.valor_t_h, aceleracao=c.settings.estadia_aceleracao,
    )


def resumo_estadia_dict(c, e: Estadia) -> dict:
    d = resumo_estadia(c, e).dict()
    d.update(estadia_id=e.id, rota_id=e.rota_id, aceleracao=c.settings.estadia_aceleracao)
    return d


def ultimos_avisos(rota_id: int, limite: int = 3) -> list[str]:
    """O que o agente avisou ao motorista por último (para "repete" e "o que eu perdi")."""
    from ..dominio.enums import TipoEvento
    from ..infra.models import Evento

    with sessao() as s:
        evs = s.exec(select(Evento).where(Evento.rota_id == rota_id, Evento.tipo == str(TipoEvento.FALA_AGENTE))
                     .order_by(Evento.id.desc()).limit(30)).all()
    avisos = [e.mensagem for e in evs if (e.dados or {}).get("destino") == "motorista"]
    return list(reversed(avisos[:limite]))
