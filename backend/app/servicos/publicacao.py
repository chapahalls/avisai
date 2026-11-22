"""Transportadora publica rotas e atribui motoristas (evento RouteAssigned do contrato do doc)."""
from typing import Optional

from sqlmodel import select

from ..dominio.enums import StatusRota, TipoEvento
from ..infra.db import sessao
from ..infra.models import Motorista, Rota
from . import consultas
from .sessoes import VozAgora


def motoristas() -> list[Motorista]:
    with sessao() as s:
        return s.exec(select(Motorista).order_by(Motorista.id)).all()


def criar_motorista(nome: str, telefone_e164: Optional[str], email: Optional[str], empresa_id: int = 1) -> Motorista:
    with sessao() as s:
        m = Motorista(empresa_id=empresa_id, nome=nome, telefone_e164=telefone_e164, email=email)
        s.add(m)
        s.commit()
        s.refresh(m)
        return m


def motorista_por_email(email: str) -> Optional[Motorista]:
    with sessao() as s:
        return s.exec(select(Motorista).where(Motorista.email == email.lower())).first()


def rota_atual(motorista_id: int) -> Optional[Rota]:
    """Rota mais recente atribuída ao motorista que ainda não terminou."""
    with sessao() as s:
        return s.exec(select(Rota).where(Rota.motorista_id == motorista_id, Rota.status != StatusRota.DESCARREGADA)
                      .order_by(Rota.atribuida_em.desc().nullslast(), Rota.id.desc())).first()


async def publicar(c, dados: dict, motorista_id: Optional[int] = None) -> Rota:
    from ..seed import trajeto

    o, d, rec = dados["origem"], dados["destino"], dados["recebedor"]
    with sessao() as s:
        r = Rota(
            empresa_id=dados.get("empresa_id") or 1,
            origem_nome=o["nome"], origem_lat=o["lat"], origem_lng=o["lng"],
            destino_nome=d["nome"], destino_lat=d["lat"], destino_lng=d["lng"],
            trajeto=trajeto(40, (o["lat"], o["lng"]), (d["lat"], d["lng"])),
            status=StatusRota.PUBLICADA, publicada_em=c.relogio.agora(),
            placa=dados.get("placa", ""), nota_fiscal=dados.get("nota_fiscal", ""),
            carga_descricao=dados.get("carga_descricao", ""), carga_t=dados.get("carga_t", 0),
            janela_descarga=dados.get("janela_descarga", ""),
            recebedor_empresa=rec["empresa"], recebedor_nome=rec["nome"], recebedor_telefone_e164=rec["telefone_e164"],
        )
        s.add(r)
        s.commit()
        s.refresh(r)
    c.eventos.registrar(TipoEvento.ROTA_PUBLICADA, f"Rota publicada: {r.origem_nome} → {r.destino_nome} ({r.carga_t:g} t).",
                        r.id, placa=r.placa, nota_fiscal=r.nota_fiscal)
    if motorista_id:
        r = await atribuir(c, r.id, motorista_id)
    return r


async def atribuir(c, rota_id: int, motorista_id: int) -> Rota:
    with sessao() as s:
        r = s.get(Rota, rota_id)
        m = s.get(Motorista, motorista_id)
        if not r:
            raise consultas.NaoEncontrado(f"rota {rota_id} não existe")
        if not m:
            raise consultas.NaoEncontrado(f"motorista {motorista_id} não existe")
        r.motorista_id, r.atribuida_em = motorista_id, c.relogio.agora()
        if r.status == StatusRota.PUBLICADA:
            r.status = StatusRota.PLANEJADA
        s.add(r)
        s.commit()
        s.refresh(r)
    c.eventos.registrar(
        TipoEvento.ROTA_ATRIBUIDA, f"Rota {r.id} atribuída a {m.nome}: {r.origem_nome} → {r.destino_nome}.", r.id,
        motorista_id=m.id, motoristaId=m.id, motorista=m.nome, origem=r.origem_nome, destino=r.destino_nome,
        carga_t=r.carga_t, janela=r.janela_descarga, _fonte="cco",
    )
    await _avisar_motorista(c, m.id, r)
    return r


async def _avisar_motorista(c, motorista_id: int, r: Rota) -> None:
    """Se o motorista estiver com o agente aberto (em qualquer rota dele), o agente anuncia a rota nova."""
    from ..infra.models import SessaoAgente

    with sessao() as s:
        sa = s.exec(select(SessaoAgente).join(Rota, Rota.id == SessaoAgente.rota_id)
                    .where(Rota.motorista_id == motorista_id, SessaoAgente.papel == "motorista",
                           SessaoAgente.status == "ativa").order_by(SessaoAgente.id.desc())).first()
    if not sa:
        return
    texto = (f"Rota nova: {r.origem_nome} para {r.destino_nome}, {r.carga_t:g} toneladas de {r.carga_descricao}"
             + (f", descarga {r.janela_descarga}." if r.janela_descarga else "."))
    await VozAgora(c).falar_motorista(sa.rota_id, texto)
