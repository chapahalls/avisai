"""Mensagens CCO→motorista, com entrega falada e thread de resposta."""
from typing import Optional

from sqlmodel import select

from ..dominio.enums import TipoEvento
from ..infra.db import sessao
from ..infra.models import MensagemMotorista
from . import auditoria, chamadas_agente, consultas
from .sessoes import VozAgora


def listar(rota_id: int) -> list[MensagemMotorista]:
    with sessao() as s:
        return s.exec(
            select(MensagemMotorista).where(MensagemMotorista.rota_id == rota_id).order_by(MensagemMotorista.id.desc())
        ).all()


def pendente(rota_id: int) -> Optional[MensagemMotorista]:
    with sessao() as s:
        return s.exec(
            select(MensagemMotorista)
            .where(MensagemMotorista.rota_id == rota_id, MensagemMotorista.status == "falada")
            .order_by(MensagemMotorista.id.desc())
        ).first()


def _atualizar(mensagem_id: int, **campos) -> MensagemMotorista:
    with sessao() as s:
        mensagem = s.get(MensagemMotorista, mensagem_id)
        for chave, valor in campos.items():
            setattr(mensagem, chave, valor)
        s.add(mensagem)
        s.commit()
        s.refresh(mensagem)
        return mensagem


async def falar_motorista(c, rota_id: int, remetente: str, texto: str) -> MensagemMotorista:
    consultas.rota(rota_id)
    remetente, texto = remetente.strip(), texto.strip()
    if not remetente or not texto:
        raise ValueError("remetente e texto são obrigatórios")
    with sessao() as s:
        mensagem = MensagemMotorista(rota_id=rota_id, remetente=remetente, texto=texto, criada_em=c.relogio.agora())
        s.add(mensagem)
        s.commit()
        s.refresh(mensagem)
    c.eventos.registrar(
        TipoEvento.MENSAGEM_MOTORISTA_ENVIADA,
        f"{remetente} enviou uma mensagem ao motorista.",
        rota_id,
        mensagem_id=mensagem.id,
        remetente=remetente,
        texto=texto,
        status="enviada",
        _fonte="cco",
    )
    auditoria.decisao(
        c,
        rota_id,
        percebeu=f"CCO solicitou uma mensagem para o motorista: {texto}",
        decidiu="Falar a mensagem pela sessão do agente.",
        executou=f"falar_motorista({rota_id}, {remetente}, texto)",
        resultado="Tentando entrega por voz.",
        prioridade="info",
        mensagem_id=mensagem.id,
    )
    fala = f"Você recebeu uma mensagem de {remetente} do CCO. A mensagem diz: {texto}. Quer responder?"
    entregue = await VozAgora(c).falar_motorista(rota_id, fala, prioridade="INTERRUPT")
    if entregue:
        mensagem = _atualizar(mensagem.id, status="falada", falada_em=c.relogio.agora())
        c.eventos.registrar(
            TipoEvento.MENSAGEM_MOTORISTA_FALADA,
            "Mensagem falada ao motorista; aguardando resposta.",
            rota_id,
            mensagem_id=mensagem.id,
            status="falada",
            _fonte="agent",
        )
        auditoria.decisao(
            c,
            rota_id,
            percebeu="A sessão de voz do motorista está ativa.",
            decidiu="Entregar a mensagem e pedir resposta.",
            executou="falar_motorista",
            resultado="Mensagem falada ao motorista.",
            prioridade="info",
            mensagem_id=mensagem.id,
        )
        return mensagem

    mensagem = _atualizar(mensagem.id, status="offline")
    c.eventos.registrar(
        TipoEvento.MOTORISTA_OFFLINE,
        "O app do motorista está offline ou sem sessão de voz ativa.",
        rota_id,
        mensagem_id=mensagem.id,
        prioridade="atencao",
        _fonte="agent",
    )
    auditoria.decisao(
        c,
        rota_id,
        percebeu="Não há sessão de voz ativa do motorista.",
        decidiu="Tentar ligar para o operador pela cascata configurada.",
        executou="ligar(operador, motorista offline)",
        resultado="Cascata de chamada iniciada.",
        prioridade="atencao",
        mensagem_id=mensagem.id,
    )
    await chamadas_agente.ligar(c, rota_id, "operador", f"Motorista offline para a mensagem: {texto}")
    return mensagem


def responder(c, rota_id: int, resposta: str, transcricao: Optional[str] = None) -> Optional[MensagemMotorista]:
    mensagem = pendente(rota_id)
    if not mensagem:
        return None
    resposta = resposta.strip()
    if not resposta:
        raise ValueError("resposta do motorista é obrigatória")
    mensagem = _atualizar(
        mensagem.id,
        status="respondida",
        resposta=resposta,
        transcricao_resposta=transcricao or resposta,
        respondida_em=c.relogio.agora(),
    )
    c.eventos.registrar(
        TipoEvento.MENSAGEM_MOTORISTA_RESPONDIDA,
        f"Motorista respondeu à mensagem de {mensagem.remetente}: {resposta}",
        rota_id,
        mensagem_id=mensagem.id,
        resposta=resposta,
        status="respondida",
        _fonte="driver",
    )
    auditoria.decisao(
        c,
        rota_id,
        percebeu=f"Motorista respondeu: {resposta}",
        decidiu="Vincular a resposta à mensagem original.",
        executou="responder_mensagem_motorista",
        resultado="Thread marcada como respondida.",
        prioridade="info",
        mensagem_id=mensagem.id,
    )
    return mensagem
