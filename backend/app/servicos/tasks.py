"""Peça 6: chegada → Task do CCO + estadia; escalonamento; confirmação; descarga; ocorrências."""
import asyncio
import logging
from typing import Optional

from sqlmodel import select

from ..dominio import escalonamento
from ..dominio.enums import StatusRota, StatusTask, TipoEvento, TipoGeo
from ..infra.db import sessao
from ..infra.models import Estadia, EventoGeo, Ocorrencia, RegraEscalonamento, Rota, TaskCCO
from . import chamados, consultas, ligacoes
from .sessoes import VozAgora

log = logging.getLogger("avisai.tasks")


def _publicar_task(c, t: TaskCCO) -> None:
    c.eventos.publicar("task", {"task": t.model_dump()}, t.rota_id)


async def on_chegada(c, rota_id: int, origem: str = "gps", transcricao: Optional[str] = None) -> TaskCCO:
    """Cria a Task e inicia a estadia (idempotente). Por voz, valida a chegada do GPS (dupla prova)."""
    agora = c.relogio.agora()
    with sessao() as s:
        r = s.get(Rota, rota_id)
        if not r:
            raise consultas.NaoEncontrado(f"rota {rota_id} não existe")
        t = s.exec(select(TaskCCO).where(TaskCCO.rota_id == rota_id, TaskCCO.tipo == "chegada")).first()
        geo = s.exec(select(EventoGeo).where(EventoGeo.rota_id == rota_id, EventoGeo.tipo == TipoGeo.CHEGADA)).first()
        if origem == "voz":
            if geo:
                geo.confirmacao_voz_transcricao, geo.confirmacao_voz_em = transcricao, agora
                if not _divergente(c, geo):  # celular × rastreador divergentes continuam não validados
                    geo.status = "validado"
                s.add(geo)
            else:
                s.add(EventoGeo(rota_id=rota_id, tipo=TipoGeo.CHEGADA, lat=r.ultima_lat, lng=r.ultima_lng,
                                distancia_m=r.distancia_m, confirmacao_voz_transcricao=transcricao,
                                confirmacao_voz_em=agora, timestamp=agora))
        if r.status != StatusRota.DESCARREGADA:
            r.status = StatusRota.NO_DESTINO
            s.add(r)
        if t:
            s.commit()
            existente = t
        else:
            existente = None
            t = TaskCCO(rota_id=rota_id, tipo="chegada", status=StatusTask.PENDENTE, criada_em=agora)
            e = Estadia(
                rota_id=rota_id,
                inicio=agora,
                capacidade_t=r.capacidade_t or r.carga_t,
                franquia_h=c.settings.estadia_franquia_h,
                valor_t_h=c.settings.estadia_valor_t_h,
            )
            s.add(t)
            s.add(e)
            s.commit()
            s.refresh(t)
            s.refresh(e)
    if existente:
        if origem == "voz":
            c.eventos.registrar(TipoEvento.CHEGADA_CONFIRMADA_VOZ, "Motorista confirmou a chegada por voz", rota_id,
                                transcricao=transcricao)
        await chamados.abrir_chegada(c, rota_id, existente.id)
        return existente
    c.eventos.registrar(TipoEvento.TASK_CRIADA, f"Task de chegada criada para o CCO (rota {rota_id}).", rota_id,
                        task_id=t.id, prioridade=t.prioridade)
    c.eventos.registrar(
        TipoEvento.CHEGADA,
        f"Carga da rota {rota_id} ({r.placa}) chegou em {r.destino_nome}. Task criada para o CCO; estadia contando.",
        rota_id, task_id=t.id, estadia_id=e.id, origem=origem,
    )
    _publicar_task(c, t)
    from . import reportes

    reportes.iniciar(c, rota_id, "checkin")  # o agente vai pedir o check-in (só o que faltar)
    await chamados.abrir_chegada(c, rota_id, t.id)
    if origem == "gps":  # dupla prova: o GPS detectou; a voz confirma
        await VozAgora(c).falar_motorista(
            rota_id, f"Parece que você chegou em {r.destino_nome}. Confirma a chegada? Já avisei o CCO e o contador "
                     "de estadia começou: são cinco horas de franquia.")
    elif origem != "voz":  # por voz, o próprio agente já responde ao motorista
        await VozAgora(c).falar_motorista(
            rota_id, "Chegada registrada. Avisei o CCO e o contador de estadia começou: são cinco horas de franquia. "
                     "Se tiver fila ou problema na doca, me fala.")
    c.em_segundo_plano(f"escalonamento-{t.id}", loop_escalonamento(c, t.id))
    return t


def _divergente(c, geo: EventoGeo) -> bool:
    return geo.divergencia_m is not None and geo.divergencia_m > c.settings.divergencia_gps_max_m


async def confirmar_retirada(c, rota_id: int, transcricao: Optional[str] = None, origem: str = "voz") -> EventoGeo:
    """Motorista confirma a retirada na origem (dupla prova: GPS + voz)."""
    agora = c.relogio.agora()
    with sessao() as s:
        r = s.get(Rota, rota_id)
        if not r:
            raise consultas.NaoEncontrado(f"rota {rota_id} não existe")
        geo = s.exec(select(EventoGeo).where(EventoGeo.rota_id == rota_id, EventoGeo.tipo == TipoGeo.RETIRADA)).first()
        if not geo:
            geo = EventoGeo(rota_id=rota_id, tipo=TipoGeo.RETIRADA, lat=r.ultima_lat, lng=r.ultima_lng, timestamp=agora)
        geo.confirmacao_voz_transcricao, geo.confirmacao_voz_em = transcricao, agora
        geo.status = "nao_validado" if _divergente(c, geo) else "validado"
        s.add(geo)
        if r.status in (StatusRota.PLANEJADA, StatusRota.NA_ORIGEM):
            r.status = StatusRota.EM_TRANSITO
            s.add(r)
        s.commit()
        s.refresh(geo)
    c.eventos.registrar(TipoEvento.RETIRADA, f"Retirada confirmada por {origem} em {r.origem_nome}.", rota_id,
                        transcricao=transcricao, validado=geo.status == "validado")
    from . import reportes

    reportes.iniciar(c, rota_id, "inicial")  # em seguida, o relatório inicial por voz
    return geo


def _regra(c, rota_id: int) -> tuple[int, float, list]:
    with sessao() as s:
        r = s.get(Rota, rota_id)
        regra = s.exec(select(RegraEscalonamento).where(RegraEscalonamento.empresa_id == r.empresa_id)).first()
    if regra:
        return regra.max_tentativas, c.settings.cco_intervalo_s, list(regra.niveis)
    return c.settings.cco_max_tentativas, c.settings.cco_intervalo_s, ["push", "painel", "ligacao"]


async def loop_escalonamento(c, task_id: int) -> None:
    with sessao() as s:
        rota_id = s.get(TaskCCO, task_id).rota_id
    max_t, intervalo, niveis = _regra(c, rota_id)
    for n in range(1, max_t + 1):
        canal, prioridade = escalonamento.nivel(n, niveis)
        with sessao() as s:
            t = s.get(TaskCCO, task_id)
            if t.status != StatusTask.PENDENTE:
                return
            t.tentativas, t.canal_atual, t.prioridade, t.ultima_notificacao = n, canal, prioridade, c.relogio.agora()
            s.add(t)
            s.commit()
            s.refresh(t)
        e = consultas.estadia_aberta(rota_id)
        x = consultas.resumo_estadia_dict(c, e) if e else {}
        c.eventos.registrar(
            TipoEvento.NOTIFICACAO_CCO,
            f"Tentativa {n}/{max_t} ({canal}): caminhão parado há {x.get('tempo_parado', '-')}, "
            f"franquia restante {x.get('franquia_restante', '-')}, estadia {x.get('valor_fmt', '-')}.",
            rota_id, task_id=task_id, tentativa=n, canal=canal, prioridade=prioridade, estadia=x,
        )
        _publicar_task(c, t)
        await asyncio.sleep(intervalo)
    with sessao() as s:
        t = s.get(TaskCCO, task_id)
        if t.status != StatusTask.PENDENTE:
            return
        t.status, t.prioridade = StatusTask.ESCALADA_RECEBEDOR, "critica"
        s.add(t)
        s.commit()
        s.refresh(t)
    c.eventos.registrar(TipoEvento.ESCALADA_RECEBEDOR,
                        f"CCO não respondeu em {max_t} tentativas. Agente vai ligar para o recebimento.", rota_id, task_id=task_id)
    _publicar_task(c, t)
    await VozAgora(c).falar_motorista(rota_id, f"O CCO não respondeu em {max_t} tentativas. Tô ligando pro recebimento agora.")
    try:
        await ligacoes.ligar(c, rota_id, motivo="cco_sem_resposta", task_id=task_id)
    except Exception as e:  # noqa: BLE001  (já registrado como ligacao_falhou)
        log.error("ligação ao recebedor falhou: %s", e)


async def confirmar(c, task_id: int, por: str = "CCO") -> TaskCCO:
    with sessao() as s:
        t = s.get(TaskCCO, task_id)
        if not t:
            raise consultas.NaoEncontrado("task não existe")
        if t.status in (StatusTask.PENDENTE, StatusTask.ESCALADA_RECEBEDOR):
            t.status, t.confirmado_em, t.confirmado_por = StatusTask.CONFIRMADA, c.relogio.agora(), por
            s.add(t)
            s.commit()
            s.refresh(t)
    c.eventos.registrar(TipoEvento.TASK_CONFIRMADA, f"{por} assumiu a Task da rota {t.rota_id}.", t.rota_id, task_id=task_id)
    _publicar_task(c, t)
    await VozAgora(c).falar_motorista(t.rota_id, "O CCO assumiu o seu caso e vai tratar com o recebedor.")
    return t


async def confirmar_descarga(c, rota_id: int, por: str = "motorista", transcricao: Optional[str] = None) -> dict:
    agora = c.relogio.agora()
    with sessao() as s:
        r = s.get(Rota, rota_id)
        if not r:
            raise consultas.NaoEncontrado(f"rota {rota_id} não existe")
        e = s.exec(select(Estadia).where(Estadia.rota_id == rota_id, Estadia.fim == None)).first()  # noqa: E711
        t = s.exec(select(TaskCCO).where(TaskCCO.rota_id == rota_id).order_by(TaskCCO.id.desc())).first()
        if e:
            e.fim = agora
            s.add(e)
        if t and t.status != StatusTask.CONCLUIDA:
            t.status, t.concluida_em = StatusTask.CONCLUIDA, agora
            s.add(t)
        r.status = StatusRota.DESCARREGADA
        s.add(r)
        s.add(EventoGeo(rota_id=rota_id, tipo=TipoGeo.DESCARGA, lat=r.ultima_lat, lng=r.ultima_lng, timestamp=agora,
                        confirmacao_voz_transcricao=transcricao, confirmacao_voz_em=agora if transcricao else None,
                        status="validado" if transcricao else "nao_validado"))
        s.commit()
        if e:
            s.refresh(e)
        if t:
            s.refresh(t)
    x = consultas.resumo_estadia_dict(c, e) if e else {}
    c.eventos.registrar(
        TipoEvento.DESCARGA,
        f"Descarga confirmada por {por}. Tempo parado {x.get('tempo_parado', '-')}, estadia {x.get('valor_fmt', '-')}.",
        rota_id, estadia=x, task_id=t.id if t else None,
    )
    if t:
        _publicar_task(c, t)
    return x


def registrar_ocorrencia(
    c,
    rota_id: int,
    tipo: str,
    descricao: str,
    transcricao: Optional[str] = None,
    km: Optional[float] = None,
    rodovia: Optional[str] = None,
) -> Ocorrencia:
    with sessao() as s:
        r = s.get(Rota, rota_id)
        if not r:
            raise consultas.NaoEncontrado("Rota não encontrada")
        from ..dominio import ocorrencias as roteiro

        # fecha ocorrências antigas ainda abertas (o motorista mudou de assunto)
        for antiga in s.exec(select(Ocorrencia).where(Ocorrencia.rota_id == rota_id, Ocorrencia.completa == False)).all():  # noqa: E712
            antiga.completa = True
            s.add(antiga)
        o = Ocorrencia(rota_id=rota_id, tipo=tipo, descricao=descricao, km=km, rodovia=rodovia,
                       lat=r.ultima_lat, lng=r.ultima_lng,
                       transcricao=transcricao, timestamp=c.relogio.agora(), faltantes=roteiro.campos(tipo))
        s.add(o)
        s.commit()
        s.refresh(o)
    c.eventos.registrar(TipoEvento.OCORRENCIA, f"Ocorrência ({tipo}): {descricao}", rota_id, ocorrencia_id=o.id, tipo_ocorrencia=tipo)
    if tipo == "atraso" and r.status in (StatusRota.PLANEJADA, StatusRota.NA_ORIGEM, StatusRota.EM_TRANSITO, StatusRota.APROXIMANDO):
        # atraso na estrada: avisa o recebedor do novo horário (quem perde a janela espera mais na chegada)
        c.em_segundo_plano(f"lig-atraso-{rota_id}", ligacoes.ligar(c, rota_id, motivo="atraso", detalhe=descricao))
    return o


def ocorrencia_aberta(rota_id: int) -> Optional[Ocorrencia]:
    with sessao() as s:
        return s.exec(select(Ocorrencia).where(Ocorrencia.rota_id == rota_id, Ocorrencia.completa == False)  # noqa: E712
                      .order_by(Ocorrencia.id.desc())).first()


def detalhar_ocorrencia(c, rota_id: int, campos: dict, transcricao: Optional[str] = None) -> dict:
    """Registra respostas do aprofundamento; devolve a próxima pergunta (uma por vez) ou fecha a ocorrência."""
    from ..dominio import ocorrencias as roteiro

    aberta = ocorrencia_aberta(rota_id)
    if not aberta:
        return {"ok": False, "mensagem": "Não há ocorrência aberta para detalhar."}
    validos = {k: str(v).strip() for k, v in (campos or {}).items() if k in roteiro.campos(aberta.tipo) and str(v).strip()}
    with sessao() as s:
        o = s.get(Ocorrencia, aberta.id)
        era_grave = roteiro.grave(o.tipo, o.detalhes or {})
        o.detalhes = {**(o.detalhes or {}), **validos}
        o.faltantes = [k for k in roteiro.campos(o.tipo) if k not in o.detalhes]
        o.completa = not o.faltantes
        s.add(o)
        s.commit()
        s.refresh(o)
    grave = roteiro.grave(o.tipo, o.detalhes)
    if grave and not era_grave:
        c.eventos.registrar(TipoEvento.OCORRENCIA_GRAVE,
                            f"URGENTE: acidente com ferido na rota {rota_id}. Motorista orientado a ligar 192/193.",
                            rota_id, ocorrencia_id=o.id, prioridade="critica", detalhes=o.detalhes)
    if o.completa:
        c.eventos.registrar(TipoEvento.OCORRENCIA_DETALHADA,
                            f"Ocorrência ({o.tipo}) detalhada: {roteiro.resumo(o.tipo, o.descricao, o.detalhes)}",
                            rota_id, ocorrencia_id=o.id, tipo_ocorrencia=o.tipo, detalhes=o.detalhes, transcricao=transcricao)
    return {"ok": True, "completa": o.completa, "grave": grave, "faltando": o.faltantes,
            "pergunte_agora": roteiro.proxima(o.tipo, o.faltantes),
            "orientacao": "Se ainda não ligaram, oriente ligar 192 (SAMU) ou 193 (Bombeiros)." if grave else None}
