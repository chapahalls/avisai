"""Sessões LiveKit para motorista, recebedor e operador."""
import asyncio
import logging
from typing import Optional

from sqlmodel import select

from ..dominio import prompts
from ..dominio.enums import Papel, StatusSessao, TipoEvento
from ..infra.db import sessao
from ..infra.models import SessaoAgente
from ..integracoes.livekit import token as token_livekit
from . import consultas

log = logging.getLogger("rodar.sessoes")

def canal_motorista(rota_id: int) -> str:
    return f"rodar-rota-{rota_id}"


def canal_recebedor(ligacao_id: int) -> str:
    return f"rodar-recebedor-{ligacao_id}"


def canal_operador(chamada_id: int) -> str:
    return f"rodar-operador-{chamada_id}"


# Prefixos de sala usados só pelas sessões reais do backend (motorista, recebedor, operador).
# O token de demo (POST /livekit/token) nunca pode assinar uma sala com esses prefixos: são
# as salas com agente dispatachado e dados de rota, protegidas pelo dono (GET /token, /sessions).
PREFIXOS_RESERVADOS = ("rodar-rota-", "rodar-recebedor-", "rodar-operador-")


def identidade_usuario(sa: SessaoAgente) -> str:
    if sa.papel == Papel.RECEBEDOR:
        return f"recebedor-{sa.ligacao_id}"
    if sa.papel == Papel.OPERADOR:
        return "operador-" + sa.canal.rsplit("-", 1)[-1]
    return f"motorista-{sa.rota_id}"


def identidade_agente(sa: SessaoAgente) -> str:
    return f"rodar-agente-{sa.id}"


def token_usuario(c, sa: SessaoAgente) -> str:
    return token_livekit(c.settings, sa.canal, identidade_usuario(sa), name=sa.papel)


def _atualizar(sessao_id: int, **campos) -> SessaoAgente:
    with sessao() as s:
        sa = s.get(SessaoAgente, sessao_id)
        for k, v in campos.items():
            setattr(sa, k, v)
        s.add(sa)
        s.commit()
        s.refresh(sa)
        return sa


async def _iniciar(c, sa: SessaoAgente, prompt: str, saudacao: str,
                   termos_rota: Optional[list[str]] = None) -> SessaoAgente:
    try:
        dispatch_id = await c.livekit.dispatch(sa.canal, {
            "session_id": sa.id,
            "role": sa.papel,
            "participant_identity": identidade_usuario(sa),
            "agent_identity": identidade_agente(sa),
            "instructions": prompt,
            "greeting": saudacao,
            "asr_keyterms": termos_rota or [],
        })
    except Exception as e:
        _atualizar(sa.id, status=StatusSessao.FALHOU, erro=str(e)[:500])
        raise
    sa = _atualizar(sa.id, agent_id=dispatch_id, status=StatusSessao.ATIVA)
    c.eventos.registrar(TipoEvento.SESSAO_INICIADA, "Agente LiveKit entrou na sala", sa.rota_id,
                        sessao_id=sa.id, livekit_dispatch_id=dispatch_id, room=sa.canal)
    return sa


_travas: dict[int, asyncio.Lock] = {}


async def iniciar_motorista(c, rota_id: int) -> SessaoAgente:
    """Um início por vez por rota, evitando dispatch duplicado ao tocar duas vezes."""
    trava = _travas.setdefault(rota_id, asyncio.Lock())
    async with trava:
        r, nome_mot, empresa = consultas.contexto_rota(rota_id)
        with sessao() as s:
            antigas = s.exec(select(SessaoAgente.id).where(
                SessaoAgente.rota_id == rota_id, SessaoAgente.papel == Papel.MOTORISTA,
                SessaoAgente.status == StatusSessao.ATIVA,
            )).all()
        for sid in antigas:
            await encerrar(c, sid)
        with sessao() as s:
            sa = SessaoAgente(rota_id=rota_id, papel=Papel.MOTORISTA, canal=canal_motorista(rota_id),
                              llm_mode="custom",
                              criada_em=c.relogio.agora())
            s.add(sa)
            s.commit()
            s.refresh(sa)
        prompt, saudacao = prompts.motorista(r, nome_mot, empresa)
        termos = [r.destino_nome, r.origem_nome, r.recebedor_empresa, r.placa, nome_mot.split()[0]]
        return await _iniciar(c, sa, prompt, saudacao, termos)


async def iniciar_operador(c, rota_id: int, chamada_id: int, motivo: str) -> SessaoAgente:
    """Despacha um agente para a sala do fallback RTC do operador."""
    r, nome_mot, _ = consultas.contexto_rota(rota_id)
    with sessao() as s:
        sa = SessaoAgente(rota_id=rota_id, papel=Papel.OPERADOR, canal=canal_operador(chamada_id),
                          llm_mode="custom",
                          criada_em=c.relogio.agora())
        s.add(sa)
        s.commit()
        s.refresh(sa)
    prompt, saudacao = prompts.operador(r, nome_mot, motivo)
    termos = [r.placa, r.destino_nome, nome_mot, "CCO", "operador"]
    return await _iniciar(c, sa, prompt, saudacao, termos)


def _eh_sip(sa: SessaoAgente) -> bool:
    from ..infra.models import LigacaoRecebedor
    if not sa.ligacao_id:
        return False
    with sessao() as s:
        lig = s.get(LigacaoRecebedor, sa.ligacao_id)
    return bool(lig and lig.modo == "sip")


async def encerrar(c, sessao_id: int) -> SessaoAgente:
    with sessao() as s:
        sa = s.get(SessaoAgente, sessao_id)
    if not sa:
        raise consultas.NaoEncontrado("sessão não existe")
    if sa.status == StatusSessao.ATIVA:
        try:
            await c.livekit.remove(sa.canal, identidade_agente(sa))
            if sa.papel == Papel.RECEBEDOR and _eh_sip(sa):
                await c.livekit.remove(sa.canal, f"sip-recebedor-{sa.ligacao_id}")
        except Exception as e:  # noqa: BLE001
            log.warning("não foi possível remover participantes da sala %s: %s", sa.canal, e)
    return _atualizar(sessao_id, status=StatusSessao.ENCERRADA, encerrada_em=c.relogio.agora())


async def falar(c, sessao_id: int, texto: str, prioridade: str = "APPEND") -> None:
    with sessao() as s:
        sa = s.get(SessaoAgente, sessao_id)
    if not sa or not sa.agent_id:
        raise consultas.NaoEncontrado("sessão não existe ou sem agente")
    if not await c.livekit.participant_present(sa.canal, identidade_agente(sa)):
        raise RuntimeError("agente ainda não entrou na sala")
    await c.livekit.send_control(sa.canal, identidade_agente(sa), {"action": "speak", "text": texto,
                                                                   "priority": prioridade})
    c.eventos.registrar(TipoEvento.FALA_AGENTE, texto, sa.rota_id, destino=sa.papel, manual=True)


class VozLiveKit:
    """Entrega avisos ao agente ativo pela sala e registra o evento mesmo offline."""

    def __init__(self, c):
        self.c = c

    async def falar_motorista(self, rota_id: int, texto: str, prioridade: str = "APPEND") -> bool:
        sa = consultas.sessao_ativa_motorista(rota_id)
        ev = self.c.eventos.registrar(TipoEvento.FALA_AGENTE, texto, rota_id, destino="motorista",
                                      entregue=bool(sa and sa.agent_id), prioridade=prioridade)
        if not sa or not sa.agent_id:
            self.c.eventos.publicar("aviso_motorista", {
                "id": ev.id, "rota_id": rota_id, "texto": texto, "prioridade": prioridade,
                "pede_resposta": texto.rstrip().endswith("?"),
            }, rota_id)
            return False
        try:
            if not await self.c.livekit.participant_present(sa.canal, identidade_agente(sa)):
                return False
            await self.c.livekit.send_control(sa.canal, identidade_agente(sa), {
                "action": "speak", "text": texto, "priority": prioridade,
            })
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("fala proativa LiveKit falhou: %s", e)
            return False
