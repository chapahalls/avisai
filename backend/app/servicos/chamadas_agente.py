"""Ligação do agente em cascata: Twilio PSTN, Agora RTC e escalonamento."""
import asyncio
from typing import Optional

from sqlmodel import select

from ..dominio.enums import TipoEvento
from ..infra.db import sessao
from ..infra.models import ChamadaAgente, Motorista
from ..integracoes.twilio import ResultadoTwilio, TwilioGateway
from . import auditoria, consultas, sessoes


def listar(rota_id: Optional[int] = None, apenas_abertas: bool = False) -> list[ChamadaAgente]:
    with sessao() as s:
        query = select(ChamadaAgente).order_by(ChamadaAgente.id.desc())
        if rota_id is not None:
            query = query.where(ChamadaAgente.rota_id == rota_id)
        if apenas_abertas:
            query = query.where(ChamadaAgente.status.in_(("iniciada", "agora_tocando")))
        return s.exec(query).all()


def obter(chamada_id: int) -> ChamadaAgente:
    with sessao() as s:
        chamada = s.get(ChamadaAgente, chamada_id)
    if not chamada:
        raise consultas.NaoEncontrado("chamada do agente não existe")
    return chamada


def _atualizar(chamada_id: int, **campos) -> ChamadaAgente:
    with sessao() as s:
        chamada = s.get(ChamadaAgente, chamada_id)
        for chave, valor in campos.items():
            setattr(chamada, chave, valor)
        s.add(chamada)
        s.commit()
        s.refresh(chamada)
        return chamada


def _numero_destino(rota_id: int, destino: str, settings) -> Optional[str]:
    if destino == "operador":
        return settings.twilio_operator_phone_e164 or None
    if destino == "supervisor":
        return settings.twilio_supervisor_phone_e164 or None
    if destino == "motorista":
        rota = consultas.rota(rota_id)
        with sessao() as s:
            motorista = s.get(Motorista, rota.motorista_id) if rota.motorista_id else None
        return motorista.telefone_e164 if motorista else None
    return None


async def _twilio(c, rota_id: int, destino: str, motivo: str) -> ResultadoTwilio:
    if not c.settings.twilio_configurada():
        return ResultadoTwilio(False, "Twilio não configurado")
    numero = _numero_destino(rota_id, destino, c.settings)
    if not numero:
        return ResultadoTwilio(False, f"Telefone de {destino} não configurado")
    gateway = getattr(c, "twilio", None) or TwilioGateway(c.settings)
    return await gateway.ligar(numero, motivo)


async def ligar(c, rota_id: int, destino: str, motivo: str, iniciado_por: str = "agent") -> ChamadaAgente:
    if destino not in ("operador", "supervisor", "motorista"):
        raise ValueError("destino de ligação inválido")
    rota = consultas.rota(rota_id)
    motivo = motivo.strip()
    if not motivo:
        raise ValueError("motivo da ligação é obrigatório")
    with sessao() as s:
        chamada = ChamadaAgente(rota_id=rota_id, destino=destino, motivo=motivo, iniciada_em=c.relogio.agora())
        s.add(chamada)
        s.commit()
        s.refresh(chamada)

    auditoria.decisao(
        c,
        rota_id,
        percebeu=f"É necessário ligar para {destino}: {motivo}",
        decidiu="Tentar ligação PSTN pelo Twilio.",
        executou=f"ligar({destino}, motivo)",
        resultado="Tentativa iniciada.",
        prioridade="atencao",
        chamada_id=chamada.id,
        iniciado_por=iniciado_por,
    )
    twilio = await _twilio(c, rota_id, destino, motivo)
    if twilio.ok:
        chamada = _atualizar(
            chamada.id,
            status="twilio_atendida",
            twilio_sid=twilio.sid,
            twilio_resultado=twilio.detalhe,
        )
        auditoria.decisao(
            c,
            rota_id,
            percebeu="Twilio configurado e destino disponível.",
            decidiu="Concluir a cascata no PSTN.",
            executou=f"Twilio Calls {twilio.sid}",
            resultado="Chamada PSTN iniciada.",
            prioridade="info",
            chamada_id=chamada.id,
        )
        return chamada

    chamada = _atualizar(chamada.id, twilio_resultado=twilio.detalhe)
    c.eventos.registrar(
        TipoEvento.CHAMADA_TWILIO_FALHOU,
        f"ligar({destino}) via Twilio falhou: {twilio.detalhe}",
        rota_id,
        chamada_id=chamada.id,
        destino=destino,
        resultado=twilio.detalhe,
        _fonte="agent",
    )
    auditoria.decisao(
        c,
        rota_id,
        percebeu=f"Twilio falhou: {twilio.detalhe}",
        decidiu="Usar o fallback Agora RTC para o navegador do operador.",
        executou="Criou uma chamada RTC do AvisAI.",
        resultado="Preparando o toque no operador.",
        prioridade="atencao",
        chamada_id=chamada.id,
    )
    try:
        sessao_operador = await sessoes.iniciar_operador(c, rota.id, chamada.id, motivo)
    except Exception as error:  # configuração Agora, rede ou join também ficam visíveis
        chamada = _atualizar(chamada.id, status="falhou", erro=str(error)[:500], encerrada_em=c.relogio.agora())
        auditoria.decisao(
            c,
            rota_id,
            percebeu=f"Fallback Agora indisponível: {error}",
            decidiu="Escalar o caso sem uma chamada RTC ativa.",
            executou="escalar_supervisor()",
            resultado="Alerta crítico publicado para a CCO.",
            prioridade="critico",
            chamada_id=chamada.id,
        )
        c.eventos.registrar(TipoEvento.ESCALADA_SUPERVISOR, "Escalada ao supervisor: Agora RTC indisponível.", rota_id,
                            chamada_id=chamada.id, prioridade="critico", _fonte="agent")
        return chamada

    chamada = _atualizar(
        chamada.id,
        status="agora_tocando",
        agora_canal=sessao_operador.canal,
        sessao_id=sessao_operador.id,
    )
    c.eventos.registrar(
        TipoEvento.CHAMADA_AGORA_INICIADA,
        "Fallback Agora RTC iniciado; aguardando o operador por até 30 segundos.",
        rota_id,
        chamada_id=chamada.id,
        canal=sessao_operador.canal,
        _fonte="agent",
    )
    auditoria.decisao(
        c,
        rota_id,
        percebeu="Twilio não completou a ligação.",
        decidiu="Tocar a chamada no navegador /operador.",
        executou="fallback Agora RTC",
        resultado="Aguardando atendimento.",
        prioridade="atencao",
        chamada_id=chamada.id,
    )
    c.em_segundo_plano(f"chamada-agente-{chamada.id}", vigiar(c, chamada.id))
    return chamada


async def atender(c, chamada_id: int) -> ChamadaAgente:
    chamada = obter(chamada_id)
    if chamada.status != "agora_tocando":
        return chamada
    chamada = _atualizar(chamada.id, status="atendida", atendida_em=c.relogio.agora())
    c.eventos.registrar(TipoEvento.CHAMADA_AGORA_ATENDIDA, "Fallback Agora RTC atendido pelo operador.", chamada.rota_id,
                        chamada_id=chamada.id, _fonte="cco")
    auditoria.decisao(
        c,
        chamada.rota_id,
        percebeu="O operador entrou na chamada RTC.",
        decidiu="Conectar o operador ao agente.",
        executou="fallback Agora RTC",
        resultado="Atendida.",
        prioridade="info",
        chamada_id=chamada.id,
    )
    return chamada


async def vigiar(c, chamada_id: int) -> None:
    await asyncio.sleep(c.settings.chamada_operador_timeout_s)
    chamada = obter(chamada_id)
    if chamada.status != "agora_tocando":
        return
    chamada = _atualizar(chamada.id, status="escalada", encerrada_em=c.relogio.agora())
    c.eventos.registrar(
        TipoEvento.CHAMADA_SEM_RESPOSTA,
        "Fallback Agora RTC sem resposta em 30 segundos.",
        chamada.rota_id,
        chamada_id=chamada.id,
        prioridade="critico",
        _fonte="agent",
    )
    c.eventos.registrar(
        TipoEvento.ESCALADA_SUPERVISOR,
        "escalar_supervisor(): chamada do agente sem resposta.",
        chamada.rota_id,
        chamada_id=chamada.id,
        prioridade="critico",
        _fonte="agent",
    )
    auditoria.decisao(
        c,
        chamada.rota_id,
        percebeu="O operador não respondeu ao toque RTC em 30 segundos.",
        decidiu="Escalar ao supervisor.",
        executou="escalar_supervisor()",
        resultado="Alerta crítico publicado na CCO.",
        prioridade="critico",
        chamada_id=chamada.id,
    )
