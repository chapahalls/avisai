"""Chamados motorista→CCO, persistidos e acompanhados por lembretes de voz."""
import asyncio
import logging
from typing import Optional

from sqlmodel import select

from ..dominio.enums import TipoEvento
from ..infra.db import sessao
from ..infra.models import ChamadoCCO
from . import consultas

log = logging.getLogger("avisai.chamados")


def _ativo(rota_id: int, tipo: Optional[str] = None) -> Optional[ChamadoCCO]:
    with sessao() as s:
        q = select(ChamadoCCO).where(
            ChamadoCCO.rota_id == rota_id,
            ChamadoCCO.status.in_(("coletando", "aguardando_cco")),
        )
        if tipo:
            q = q.where(ChamadoCCO.tipo == tipo)
        return s.exec(q.order_by(ChamadoCCO.id.desc())).first()


def coleta_ocorrencia(rota_id: int) -> Optional[ChamadoCCO]:
    return _ativo(rota_id, "ocorrencia")


def listar(rota_id: Optional[int] = None, apenas_abertos: bool = False) -> list[ChamadoCCO]:
    with sessao() as s:
        q = select(ChamadoCCO).order_by(ChamadoCCO.id.desc())
        if rota_id is not None:
            q = q.where(ChamadoCCO.rota_id == rota_id)
        if apenas_abertos:
            q = q.where(ChamadoCCO.status.in_(("coletando", "aguardando_cco")))
        return s.exec(q).all()


def iniciar_coleta(c, rota_id: int, transcricao: Optional[str] = None) -> ChamadoCCO:
    consultas.rota(rota_id)
    existente = coleta_ocorrencia(rota_id)
    if existente:
        return existente
    with sessao() as s:
        chamado = ChamadoCCO(
            rota_id=rota_id,
            tipo="ocorrencia",
            assunto="Ocorrência em rota",
            descricao="",
            status="coletando",
            max_tentativas=c.settings.chamado_cco_max_tentativas,
            intervalo_s=c.settings.chamado_cco_intervalo_s,
            criada_em=c.relogio.agora(),
            transcricao=transcricao,
        )
        s.add(chamado)
        s.commit()
        s.refresh(chamado)
        return chamado


def atualizar_coleta(
    c,
    rota_id: int,
    *,
    descricao: Optional[str] = None,
    km: Optional[float] = None,
    rodovia: Optional[str] = None,
    transcricao: Optional[str] = None,
) -> ChamadoCCO:
    chamado = iniciar_coleta(c, rota_id, transcricao)
    with sessao() as s:
        atual = s.get(ChamadoCCO, chamado.id)
        if descricao and descricao.strip():
            atual.descricao = descricao.strip()
        if km is not None:
            atual.km = km
        if rodovia and rodovia.strip():
            atual.rodovia = rodovia.strip()
        if transcricao:
            atual.transcricao = transcricao
        s.add(atual)
        s.commit()
        s.refresh(atual)
        return atual


async def abrir(
    c,
    rota_id: int,
    tipo: str,
    assunto: str,
    descricao: str,
    *,
    km: Optional[float] = None,
    rodovia: Optional[str] = None,
    ocorrencia_id: Optional[int] = None,
    transcricao: Optional[str] = None,
) -> ChamadoCCO:
    consultas.rota(rota_id)
    if not descricao.strip():
        raise ValueError("descrição do chamado é obrigatória")
    with sessao() as s:
        existing = s.exec(select(ChamadoCCO).where(
            ChamadoCCO.rota_id == rota_id,
            ChamadoCCO.tipo == tipo,
            ChamadoCCO.status.in_(("coletando", "aguardando_cco")),
        ).order_by(ChamadoCCO.id.desc())).first()
        if existing:
            chamado = existing
            chamado.assunto = assunto
            chamado.descricao = descricao
            chamado.km = km
            chamado.rodovia = rodovia
            chamado.ocorrencia_id = ocorrencia_id
            chamado.transcricao = transcricao or chamado.transcricao
            chamado.status = "aguardando_cco"
        else:
            chamado = ChamadoCCO(
                rota_id=rota_id,
                tipo=tipo,
                assunto=assunto,
                descricao=descricao,
                km=km,
                rodovia=rodovia,
                ocorrencia_id=ocorrencia_id,
                status="aguardando_cco",
                max_tentativas=c.settings.chamado_cco_max_tentativas,
                intervalo_s=c.settings.chamado_cco_intervalo_s,
                criada_em=c.relogio.agora(),
                transcricao=transcricao,
            )
        s.add(chamado)
        s.commit()
        s.refresh(chamado)
    c.eventos.registrar(
        TipoEvento.CHAMADO_CCO_ABERTO,
        f"Motorista abriu chamado ao CCO: {assunto}.",
        rota_id,
        chamado_id=chamado.id,
        chamado=chamado.model_dump(),
        tipo_chamado=tipo,
        _fonte="driver",
    )
    c.eventos.publicar("chamado", {"chamado": chamado.model_dump()}, rota_id)
    c.em_segundo_plano(f"chamado-cco-{chamado.id}", monitorar(c, chamado.id))
    return chamado


async def abrir_ocorrencia(c, rota_id: int, ocorrencia, transcricao: Optional[str] = None) -> ChamadoCCO:
    return await abrir(
        c,
        rota_id,
        "ocorrencia",
        f"Ocorrência na rota {rota_id}",
        ocorrencia.descricao,
        km=ocorrencia.km,
        rodovia=ocorrencia.rodovia,
        ocorrencia_id=ocorrencia.id,
        transcricao=transcricao or ocorrencia.transcricao,
    )


async def abrir_chegada(c, rota_id: int, task_id: int, mensagem: Optional[str] = None) -> ChamadoCCO:
    with sessao() as s:
        existente = s.exec(
            select(ChamadoCCO)
            .where(ChamadoCCO.rota_id == rota_id, ChamadoCCO.tipo == "chegada")
            .order_by(ChamadoCCO.id.desc())
        ).first()
        if existente:
            return existente
    return await abrir(
        c,
        rota_id,
        "chegada",
        "Motorista chegou à entrega",
        mensagem or "Cheguei na entrega e estou aguardando orientação do CCO.",
    )


async def responder(c, chamado_id: int, resposta: str, respondido_por: str = "CCO") -> ChamadoCCO:
    texto = resposta.strip()
    if not texto:
        raise ValueError("resposta do CCO é obrigatória")
    with sessao() as s:
        chamado = s.get(ChamadoCCO, chamado_id)
        if not chamado:
            raise consultas.NaoEncontrado("chamado não existe")
        if chamado.status not in ("coletando", "aguardando_cco"):
            return chamado
        chamado.status = "respondido"
        chamado.resposta = texto
        chamado.respondido_por = respondido_por
        chamado.respondida_em = c.relogio.agora()
        s.add(chamado)
        s.commit()
        s.refresh(chamado)
    c.eventos.registrar(
        TipoEvento.CHAMADO_CCO_RESPONDIDO,
        f"CCO respondeu ao motorista: {texto}",
        chamado.rota_id,
        chamado_id=chamado.id,
        resposta=texto,
        respondido_por=respondido_por,
        _fonte="cco",
    )
    c.eventos.publicar("chamado", {"chamado": chamado.model_dump()}, chamado.rota_id)
    from .sessoes import VozLiveKit

    await VozLiveKit(c).falar_motorista(chamado.rota_id, f"O CCO respondeu: {texto}", prioridade="INTERRUPT")
    return chamado


async def monitorar(c, chamado_id: int) -> None:
    for tentativa in range(1, 6):
        with sessao() as s:
            chamado = s.get(ChamadoCCO, chamado_id)
        if not chamado or chamado.status != "aguardando_cco":
            return
        await asyncio.sleep(chamado.intervalo_s)
        with sessao() as s:
            chamado = s.get(ChamadoCCO, chamado_id)
            if not chamado or chamado.status != "aguardando_cco":
                return
            chamado.tentativas = tentativa
            chamado.ultima_notificacao = c.relogio.agora()
            s.add(chamado)
            s.commit()
            s.refresh(chamado)
        c.eventos.registrar(
            TipoEvento.CHAMADO_CCO_LEMBRETE,
            f"Ainda sem resposta do CCO ({tentativa}/{chamado.max_tentativas}).",
            chamado.rota_id,
            chamado_id=chamado.id,
            tentativa=tentativa,
            max_tentativas=chamado.max_tentativas,
        )
        c.eventos.publicar("chamado", {"chamado": chamado.model_dump()}, chamado.rota_id)
        from .sessoes import VozLiveKit

        await VozLiveKit(c).falar_motorista(
            chamado.rota_id,
            f"Ainda não recebi uma resposta do CCO. Tentativa {tentativa} de {chamado.max_tentativas}.",
        )
    with sessao() as s:
        chamado = s.get(ChamadoCCO, chamado_id)
        if not chamado or chamado.status != "aguardando_cco":
            return
        chamado.status = "timeout"
        s.add(chamado)
        s.commit()
        s.refresh(chamado)
    c.eventos.registrar(
        TipoEvento.CHAMADO_CCO_TIMEOUT,
        "O CCO não respondeu após cinco tentativas.",
        chamado.rota_id,
        chamado_id=chamado.id,
        tentativas=chamado.tentativas,
    )
    c.eventos.publicar("chamado", {"chamado": chamado.model_dump()}, chamado.rota_id)
    from .sessoes import VozLiveKit

    await VozLiveKit(c).falar_motorista(
        chamado.rota_id,
        "O CCO não respondeu após cinco tentativas. Vou deixar o chamado registrado para acompanhamento.",
    )
