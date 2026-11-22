"""Peça 7: ligação ao recebedor. Estratégias (porta Discador): RTC = plano B, SIP = plano A."""
import asyncio
import logging
from typing import Optional

from ..dominio import agora_payload, prompts
from ..dominio.enums import ModoLigacao, Papel, StatusLigacao, StatusSessao, TipoEvento
from ..infra.db import sessao
from ..infra.models import LigacaoRecebedor, SessaoAgente, TaskCCO
from ..integracoes import tokens
from ..integracoes.tunel import url_publica
from . import consultas, sessoes

log = logging.getLogger("avisai.ligacoes")


class DiscadorRTC:
    """Plano B: segundo agente num canal RTC; o recebedor atende pela página /recebedor."""

    modo = ModoLigacao.RTC

    def __init__(self, c):
        self.c = c

    async def ligar(self, corpo_join: dict, numero: str) -> str:
        return await self.c.agora.join(corpo_join)

    async def encerrar(self, agent_id: str, canal: str, agent_uid: int) -> None:
        await self.c.agora.leave(agent_id, canal, agent_uid)

    async def estado(self, agent_id: str, canal: str, agent_uid: int) -> Optional[str]:
        return None


class DiscadorSIP:
    """Plano A: ligação telefônica real (POST /call). Exige número importado na Agora."""

    modo = ModoLigacao.SIP

    def __init__(self, c):
        self.c = c

    async def ligar(self, corpo_join: dict, numero: str) -> str:
        s = self.c.settings
        if not s.agora_sip_from_number:
            raise RuntimeError("AGORA_SIP_FROM_NUMBER não configurado (número importado na Agora)")
        canal = corpo_join["properties"]["channel"]
        corpo = agora_payload.montar_call(
            corpo_join, para=numero, de=s.agora_sip_from_number, sip_uid=sessoes.UID_RECEBEDOR,
            sip_token=tokens.token_rtc(s, canal, sessoes.UID_RECEBEDOR),
        )
        return await self.c.agora.call(corpo)

    async def encerrar(self, agent_id: str, canal: str, agent_uid: int) -> None:
        await self.c.agora.hangup(agent_id, canal, agent_uid)

    async def estado(self, agent_id: str, canal: str, agent_uid: int) -> Optional[str]:
        return (await self.c.agora.call_status(agent_id, canal, agent_uid)).get("state")


def discador(c, modo: str):
    return DiscadorSIP(c) if modo == ModoLigacao.SIP else DiscadorRTC(c)


def _atualizar(modelo, id_, **campos):
    with sessao() as s:
        x = s.get(modelo, id_)
        for k, v in campos.items():
            setattr(x, k, v)
        s.add(x)
        s.commit()
        s.refresh(x)
        return x


async def ligar(c, rota_id: int, motivo: str, task_id: Optional[int] = None) -> LigacaoRecebedor:
    r, nome_mot, empresa = consultas.contexto_rota(rota_id)
    modo = ModoLigacao.SIP if c.settings.recebedor_modo == ModoLigacao.SIP else ModoLigacao.RTC
    with sessao() as s:
        lig = LigacaoRecebedor(task_id=task_id, rota_id=rota_id, motivo=motivo, modo=modo,
                               numero=r.recebedor_telefone_e164, iniciada_em=c.relogio.agora())
        s.add(lig)
        s.commit()
        s.refresh(lig)
        lig.canal = sessoes.canal_recebedor(lig.id)
        sa = SessaoAgente(rota_id=rota_id, papel=Papel.RECEBEDOR, ligacao_id=lig.id, canal=lig.canal,
                          agent_uid=sessoes.UID_AGENTE_RECEBEDOR, user_uid=sessoes.UID_RECEBEDOR,
                          llm_mode="custom", criada_em=c.relogio.agora())
        s.add(sa)
        s.commit()
        s.refresh(sa)
        lig.sessao_id = sa.id
        s.add(lig)
        s.commit()
        s.refresh(lig)

    e = consultas.estadia_aberta(rota_id)
    parado = None
    if e:
        from ..dominio.estadia import falar_horas

        parado = falar_horas(consultas.resumo_estadia(c, e).horas_paradas)
    try:
        prompt, abertura = prompts.recebedor(r, nome_mot, empresa, motivo, parado)
        url = sessoes.llm_url(c, sa.id)
        if not url:
            raise RuntimeError("a ligação ao recebedor exige LLM_MODE=custom (ferramenta registrar_resposta_recebedor)")
        corpo = agora_payload.montar_join(
            agora_payload.ConfigVoz.de(c.settings),
            nome=agora_payload.nome_unico(f"avisai-recebedor-l{lig.id}"),
            canal=lig.canal, token=tokens.token_agente(c.settings, lig.canal, sa.agent_uid),
            agent_uid=sa.agent_uid, remote_uid=sa.user_uid, prompt=prompt, saudacao=abertura,
            voice_id=c.settings.tts_voice_id_recebedor, llm_url=url, sessao_id=sa.id, idle_timeout=60,
        )
        try:
            agent_id = await discador(c, modo).ligar(corpo, lig.numero)
        except Exception as e_sip:
            if modo != ModoLigacao.SIP:
                raise
            c.eventos.registrar(TipoEvento.FALLBACK_PLANO_B, f"Ligação telefônica falhou ({e_sip}); seguindo pelo canal RTC.",
                                rota_id, ligacao_id=lig.id)
            modo = ModoLigacao.RTC
            agent_id = await discador(c, modo).ligar(corpo, lig.numero)
    except Exception as e_fim:
        _atualizar(LigacaoRecebedor, lig.id, status=StatusLigacao.FALHOU, erro=str(e_fim)[:500], encerrada_em=c.relogio.agora())
        _atualizar(SessaoAgente, sa.id, status=StatusSessao.FALHOU, erro=str(e_fim)[:500])
        c.eventos.registrar(TipoEvento.LIGACAO_FALHOU, f"Falha ao ligar para o recebedor: {e_fim}", rota_id, ligacao_id=lig.id)
        raise

    lig = _atualizar(LigacaoRecebedor, lig.id, agent_id=agent_id, status=StatusLigacao.EM_ANDAMENTO, modo=modo)
    _atualizar(SessaoAgente, sa.id, agent_id=agent_id, status=StatusSessao.ATIVA)
    extra = {}
    if modo == ModoLigacao.RTC:
        extra["pagina_recebedor"] = f"{url_publica(c.settings)}/recebedor?ligacao={lig.id}"
    c.eventos.registrar(
        TipoEvento.LIGACAO_RECEBEDOR,
        f"Agente ligando para {r.recebedor_nome} ({r.recebedor_empresa}) em {lig.numero} "
        f"[{'telefone' if modo == ModoLigacao.SIP else 'canal RTC, plano B'}].",
        rota_id, ligacao_id=lig.id, modo=modo, motivo=motivo, canal=lig.canal, **extra,
    )
    if motivo == "aproximacao":  # ReceiverNotified: condição para a estadia (decisão do TJMT)
        c.eventos.registrar(TipoEvento.AVISO_RECEBEDOR, f"Recebedor avisado antes da chegada (previsão {int(r.eta_min or 0)} min).",
                            rota_id, ligacao_id=lig.id, eta_min=r.eta_min)
    c.em_segundo_plano(f"vigia-lig-{lig.id}", _vigiar(c, lig.id))
    return lig


async def _vigiar(c, ligacao_id: int) -> None:
    """Acompanha a ligação; sem resposta até o timeout, registra a tentativa como prova."""
    decorrido = 0.0
    passo = c.settings.ligacao_poll_s
    while decorrido < c.settings.ligacao_timeout_s:
        await asyncio.sleep(passo)
        decorrido += passo
        with sessao() as s:
            lig = s.get(LigacaoRecebedor, ligacao_id)
        if lig.status != StatusLigacao.EM_ANDAMENTO:
            return
        try:
            estado = await discador(c, lig.modo).estado(lig.agent_id, lig.canal, sessoes.UID_AGENTE_RECEBEDOR)
        except Exception:  # noqa: BLE001
            estado = None
        if estado == "answered" and not lig.atendida:
            _atualizar(LigacaoRecebedor, ligacao_id, atendida=True)
        if estado == "hangup":
            break
    with sessao() as s:
        lig = s.get(LigacaoRecebedor, ligacao_id)
    if lig.status != StatusLigacao.EM_ANDAMENTO:
        return
    lig = _atualizar(LigacaoRecebedor, ligacao_id, status=StatusLigacao.NAO_ATENDIDA, encerrada_em=c.relogio.agora())
    c.eventos.registrar(
        TipoEvento.LIGACAO_NAO_ATENDIDA,
        f"Recebedor não respondeu à ligação das {lig.iniciada_em:%H:%M} UTC para {lig.numero}. Tentativa registrada como prova.",
        lig.rota_id, ligacao_id=ligacao_id, atendida=lig.atendida,
    )
    await sessoes.VozAgora(c).falar_motorista(
        lig.rota_id, "O recebimento não atendeu. Deixei a tentativa registrada como prova pra estadia, e o CCO tá sabendo.")
    if lig.sessao_id:
        await sessoes.encerrar(c, lig.sessao_id)


def _frase_motorista(previsao: Optional[str], doca: Optional[str], motivo: Optional[str], resumo: str) -> str:
    partes = []
    if doca:
        partes.append(str(doca) if str(doca).lower().startswith("doca") else f"a doca {doca}")
    if previsao:
        partes.append(f"libera {previsao}" if partes else f"a previsão é {previsao}")
    frase = " ".join(partes) if partes else resumo.rstrip(".")
    texto = f"Falei com o recebimento. Disseram que {frase}."
    if motivo:
        texto += f" Motivo: {motivo}."
    return texto


def regra_nao_recebe(rota_id: int) -> str:
    from sqlmodel import select

    from ..infra.models import RegraEscalonamento, Rota

    with sessao() as s:
        r = s.get(Rota, rota_id)
        regra = s.exec(select(RegraEscalonamento).where(RegraEscalonamento.empresa_id == r.empresa_id)).first()
    return regra.acao_nao_recebe if regra else "Aguardar orientação do CCO."


async def registrar_resposta(c, sessao_id: int, previsao: Optional[str], doca: Optional[str],
                             motivo: Optional[str], resumo: str, recebe_hoje: Optional[bool] = None) -> LigacaoRecebedor:
    with sessao() as s:
        sa = s.get(SessaoAgente, sessao_id)
        lig = s.get(LigacaoRecebedor, sa.ligacao_id)
        lig.atendida = True
        lig.status = StatusLigacao.RESPONDIDA
        lig.previsao, lig.doca, lig.motivo_espera, lig.resposta_resumo = previsao, doca, motivo, resumo
        lig.enviada_cco_em = c.relogio.agora()
        lig.encerrada_em = c.relogio.agora()
        s.add(lig)
        if lig.task_id:
            t = s.get(TaskCCO, lig.task_id)
            t.resposta_recebedor = resumo
            s.add(t)
        s.commit()
        s.refresh(lig)
    c.eventos.registrar(TipoEvento.RESPOSTA_RECEBEDOR, f"Recebedor respondeu: {resumo}", lig.rota_id,
                        ligacao_id=lig.id, task_id=lig.task_id, previsao=previsao, doca=doca, motivo=motivo)
    if lig.task_id:
        c.eventos.publicar("task", {"task": consultas_task(lig.task_id)}, lig.rota_id)
    if recebe_hoje is False:
        regra = regra_nao_recebe(lig.rota_id)
        c.eventos.registrar(TipoEvento.NAO_RECEBE_HOJE, f"Recebedor não recebe hoje ({previsao or resumo}). Regra: {regra}",
                            lig.rota_id, ligacao_id=lig.id, previsao=previsao, regra=regra)
        texto = f"O recebimento disse que hoje não recebe, {previsao or 'sem previsão'}. Pela regra da transportadora: {regra}"
    else:
        texto = _frase_motorista(previsao, doca, motivo, resumo)
    entregue = await sessoes.VozAgora(c).falar_motorista(lig.rota_id, texto, prioridade="INTERRUPT")
    if entregue:
        _atualizar(LigacaoRecebedor, lig.id, enviada_motorista_em=c.relogio.agora())
    c.em_segundo_plano(f"encerrar-lig-{lig.id}", _encerrar_depois(c, sessao_id, c.settings.encerrar_ligacao_apos_s))
    return lig


def consultas_task(task_id: int) -> dict:
    with sessao() as s:
        return s.get(TaskCCO, task_id).model_dump()


async def _encerrar_depois(c, sessao_id: int, seg: float) -> None:
    await asyncio.sleep(seg)  # dá tempo de o agente se despedir
    await sessoes.encerrar(c, sessao_id)
