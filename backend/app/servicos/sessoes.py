"""Sessões de agente (motorista) e fala proativa (porta Voz)."""
import asyncio
import logging
from typing import Optional

from sqlmodel import select

from ..dominio import agora_payload, prompts
from ..dominio.enums import Papel, StatusSessao, TipoEvento
from ..infra.db import sessao
from ..infra.models import SessaoAgente
from ..integracoes import tokens
from ..integracoes.agora_rest import AgoraErro
from ..integracoes.tunel import url_publica
from . import consultas

log = logging.getLogger("avisai.sessoes")

UID_MOTORISTA = 1001
UID_CCO = 2001
UID_RECEBEDOR = 3001
UID_AGENTE_MOTORISTA = 9001
UID_AGENTE_RECEBEDOR = 9002
UID_AGENTE_OPERADOR = 9003


def canal_motorista(rota_id: int) -> str:
    return f"avisai-rota-{rota_id}"


def canal_recebedor(ligacao_id: int) -> str:
    return f"avisai-recebedor-{ligacao_id}"


def canal_operador(chamada_id: int) -> str:
    return f"avisai-operador-{chamada_id}"


def llm_url(c, sessao_id: int, exigir_auditoria: bool = False) -> Optional[str]:
    """Retorna o gateway local de LLM para sessões que precisam ser auditáveis.

    O LLM gerenciado pela Agora não envia falas nem tool calls ao backend.
    Motorista e operador, portanto, sempre passam pelo gateway local para que
    alertas, decisões e mensagens sejam publicados no SSE da CCO.
    """
    if not exigir_auditoria and c.settings.llm_mode != "custom":
        return None
    base = url_publica(c.settings)
    if not base:
        raise RuntimeError("Sem URL pública: suba o túnel ou defina PUBLIC_URL (a Agora precisa alcançar /v1/chat/completions)")
    return f"{base}/v1/chat/completions?sessao={sessao_id}"


def _atualizar(sessao_id: int, **campos) -> SessaoAgente:
    with sessao() as s:
        sa = s.get(SessaoAgente, sessao_id)
        for k, v in campos.items():
            setattr(sa, k, v)
        s.add(sa)
        s.commit()
        s.refresh(sa)
        return sa


_travas: dict[int, asyncio.Lock] = {}


async def iniciar_motorista(c, rota_id: int) -> SessaoAgente:
    """Um início por vez por rota (clique duplo não cria dois agentes com o mesmo uid)."""
    trava = _travas.setdefault(rota_id, asyncio.Lock())
    async with trava:
        return await _iniciar_motorista(c, rota_id)


async def _iniciar_motorista(c, rota_id: int) -> SessaoAgente:
    r, nome_mot, empresa = consultas.contexto_rota(rota_id)
    # Um agente por canal: dois com o uid 9001 se derrubam. Tira os antigos antes do /join novo.
    with sessao() as s:
        antigas = s.exec(select(SessaoAgente.id).where(
            SessaoAgente.rota_id == rota_id, SessaoAgente.papel == Papel.MOTORISTA,
            SessaoAgente.status == StatusSessao.ATIVA,
        )).all()
    for sid in antigas:
        await encerrar(c, sid)
    with sessao() as s:
        sa = SessaoAgente(rota_id=rota_id, papel=Papel.MOTORISTA, canal=canal_motorista(rota_id),
                          agent_uid=UID_AGENTE_MOTORISTA, user_uid=UID_MOTORISTA, llm_mode="custom",
                          criada_em=c.relogio.agora())
        s.add(sa)
        s.commit()
        s.refresh(sa)
    try:
        prompt, saudacao = prompts.motorista(r, nome_mot, empresa)
        corpo = agora_payload.montar_join(
            agora_payload.ConfigVoz.de(c.settings),
            nome=agora_payload.nome_unico(f"avisai-motorista-r{rota_id}"),
            canal=sa.canal, token=tokens.token_agente(c.settings, sa.canal, sa.agent_uid),
            agent_uid=sa.agent_uid, remote_uid=sa.user_uid, prompt=prompt, saudacao=saudacao,
            voice_id=c.settings.tts_voice_id, llm_url=llm_url(c, sa.id, exigir_auditoria=True), sessao_id=sa.id, idle_timeout=300,
            termos_rota=[r.destino_nome, r.origem_nome, r.recebedor_empresa, r.placa, nome_mot.split()[0]],
        )
        agent_id = await c.agora.join(corpo)
    except Exception as e:
        _atualizar(sa.id, status=StatusSessao.FALHOU, erro=str(e)[:500])
        raise
    sa = _atualizar(sa.id, agent_id=agent_id, status=StatusSessao.ATIVA)
    c.eventos.registrar(TipoEvento.SESSAO_INICIADA, "Agente de voz entrou no canal do motorista", rota_id,
                        sessao_id=sa.id, agent_id=agent_id)
    return sa


async def iniciar_operador(c, rota_id: int, chamada_id: int, motivo: str) -> SessaoAgente:
    """Abre o agente que atende o operador no fallback RTC."""
    r, nome_mot, _ = consultas.contexto_rota(rota_id)
    with sessao() as s:
        sa = SessaoAgente(
            rota_id=rota_id,
            papel=Papel.OPERADOR,
            canal=canal_operador(chamada_id),
            agent_uid=UID_AGENTE_OPERADOR,
            user_uid=UID_CCO,
            llm_mode="custom",
            criada_em=c.relogio.agora(),
        )
        s.add(sa)
        s.commit()
        s.refresh(sa)
    try:
        prompt, saudacao = prompts.operador(r, nome_mot, motivo)
        corpo = agora_payload.montar_join(
            agora_payload.ConfigVoz.de(c.settings),
            nome=agora_payload.nome_unico(f"avisai-operador-c{chamada_id}"),
            canal=sa.canal,
            token=tokens.token_agente(c.settings, sa.canal, sa.agent_uid),
            agent_uid=sa.agent_uid,
            remote_uid=sa.user_uid,
            prompt=prompt,
            saudacao=saudacao,
            voice_id=c.settings.tts_voice_id,
            llm_url=llm_url(c, sa.id, exigir_auditoria=True),
            sessao_id=sa.id,
            idle_timeout=max(30, int(c.settings.chamada_operador_timeout_s) + 30),
            termos_rota=[r.placa, r.destino_nome, nome_mot, "CCO", "operador"],
        )
        agent_id = await c.agora.join(corpo)
    except Exception as error:
        _atualizar(sa.id, status=StatusSessao.FALHOU, erro=str(error)[:500])
        raise
    return _atualizar(sa.id, agent_id=agent_id, status=StatusSessao.ATIVA)


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
    if sa.agent_id and sa.status == StatusSessao.ATIVA:
        try:
            if sa.papel == Papel.RECEBEDOR and _eh_sip(sa):
                await c.agora.hangup(sa.agent_id, sa.canal, sa.agent_uid)
            else:
                await c.agora.leave(sa.agent_id, sa.canal, sa.agent_uid)
        except AgoraErro as e:
            log.warning("leave falhou: %s", e)
    return _atualizar(sessao_id, status=StatusSessao.ENCERRADA, encerrada_em=c.relogio.agora())


async def falar(c, sessao_id: int, texto: str, prioridade: str = "APPEND") -> None:
    with sessao() as s:
        sa = s.get(SessaoAgente, sessao_id)
    if not sa or not sa.agent_id:
        raise consultas.NaoEncontrado("sessão não existe ou sem agente")
    await c.agora.speak(sa.agent_id, texto, prioridade, sa.canal, sa.agent_uid)
    c.eventos.registrar(TipoEvento.FALA_AGENTE, texto, sa.rota_id, destino=sa.papel, manual=True)


class VozAgora:
    """Porta Voz: fala com o motorista se houver sessão ativa; sempre registra o evento."""

    def __init__(self, c):
        self.c = c

    async def falar_motorista(self, rota_id: int, texto: str, prioridade: str = "APPEND") -> bool:
        sa = consultas.sessao_ativa_motorista(rota_id)
        self.c.eventos.registrar(TipoEvento.FALA_AGENTE, texto, rota_id, destino="motorista",
                                 entregue=bool(sa and sa.agent_id), prioridade=prioridade)
        if not sa or not sa.agent_id:
            return False
        try:
            await self.c.agora.speak(sa.agent_id, texto, prioridade, sa.canal, sa.agent_uid)
            return True
        except AgoraErro as e:
            log.warning("speak falhou: %s", e)
            return False
