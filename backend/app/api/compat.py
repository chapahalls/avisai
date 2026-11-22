"""Compatibilidade com docs/arquitetura-avisai.md (o contrato que os fronts seguem).

Rotas do `agent-server` do doc em cima dos serviços deste backend:
  POST /agent/start · POST /agent/stop · POST /call/receiver
  POST /events (outbox idempotente) · GET /events (DomainEvent)
  GET /api/route · /api/receivers · /api/documents · /api/metrics · POST /auth/sso
"""
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from ..dominio.enums import TipoEvento
from ..infra.db import sessao
from ..infra.eventos import serial
from ..infra.models import Evento, SessaoAgente
from ..integracoes import tokens
from ..servicos import consultas, ligacoes, metricas, publicacao, reportes, sessoes, tasks, usuarios
from .deps import c, erro_http
from .schemas import DomainEventIn, SsoOut

router = APIRouter(tags=["compat (docs/arquitetura-avisai.md)"])

# TipoEvento (backend) -> EventType (contrato do doc). Os do contrato primeiro; o resto são extensões.
TIPO_DOMINIO = {
    "retirada": "PickupConfirmed",
    "relatorio": "ReportSubmitted",
    "campo_faltante": "ReportFieldMissing",
    "ocorrencia": "OccurrenceCreated",
    "aproximacao": "ApproachDetected",
    "aviso_recebedor": "ReceiverNotified",
    "resposta_recebedor": "ReceiverCallResult",
    "ligacao_nao_atendida": "ReceiverCallResult",
    "chegada": "ArrivalRegistered",
    "task_criada": "TaskCreated",
    "notificacao_cco": "TaskEscalated",
    "escalada_recebedor": "TaskEscalated",
    "task_confirmada": "TaskAcknowledged",
    "descarga": "UnloadConfirmed",
    "rota_atribuida": "RouteAssigned",
    "pergunta_documento": "DocumentQuestionAnswered",
    "ocorrencia_detalhada": "OccurrenceDetailed",
    "ocorrencia_grave": "OccurrenceCritical",
    "arquivo_adicionado": "TripFileAdded",
    "rota_publicada": "RoutePublished",
    # extensões (fora da lista do doc)
    "sessao_iniciada": "AgentSessionStarted",
    "retirada_detectada": "PickupGeofenceEntered",
    "chegada_confirmada_voz": "ArrivalVoiceConfirmed",
    "ligacao_recebedor": "ReceiverCallStarted",
    "ligacao_falhou": "ReceiverCallFailed",
    "fallback_plano_b": "ReceiverCallFallback",
    "nao_recebe_hoje": "ReceiverRefusedToday",
    "pedido_central": "CentralRequestSent",
    "resposta_central": "CentralRequestAnswered",
    "divergencia_gps": "GpsDivergence",
    "fala_motorista": "VoiceTranscript",
    "fala_recebedor": "VoiceTranscript",
    "fala_agente": "VoiceTranscript",
}
FONTE = {"arquivo_adicionado": "cco", "rota_publicada": "cco", "rota_atribuida": "cco", "fala_motorista": "driver", "fala_recebedor": "agent", "fala_agente": "agent", "task_confirmada": "cco",
         "pedido_central": "cco", "aproximacao": "system", "chegada": "system", "retirada_detectada": "system"}


def para_dominio(ev: Evento) -> dict:
    payload: dict[str, Any] = {"mensagem": ev.mensagem, **(ev.dados or {})}
    if ev.tipo == "resposta_recebedor":
        payload["answered"] = True
    elif ev.tipo == "ligacao_nao_atendida":
        payload["answered"] = False
    elif ev.tipo.startswith("fala_"):
        payload["speaker"] = ev.tipo.removeprefix("fala_")
    return {
        "id": f"evt-{ev.id}",
        "idempotencyKey": ev.idempotency_key or f"srv-{ev.id}",
        "tripId": str(ev.rota_id) if ev.rota_id is not None else None,
        "type": TIPO_DOMINIO.get(ev.tipo, ev.tipo),
        "occurredAt": (ev.dados or {}).get("occurredAt") or serial(ev.timestamp),
        "receivedAt": serial(ev.timestamp),
        "source": ev.source if ev.source != "system" else FONTE.get(ev.tipo, "agent" if ev.tipo in TIPO_DOMINIO else "system"),
        "payload": payload,
    }


def _rota_id(trip: Optional[str], padrao: int = 1) -> int:
    try:
        return int(str(trip).removeprefix("trip-")) if trip not in (None, "") else padrao
    except ValueError:
        return padrao


# ---------------- agente ----------------

class AgentStart(BaseModel):
    tripId: Optional[str] = None
    rota_id: Optional[int] = None


class AgentStop(BaseModel):
    sessionId: Optional[int] = None
    agentId: Optional[str] = None


@router.post("/agent/start")
async def agent_start(body: AgentStart = AgentStart(), ct=Depends(c)):
    try:
        sa = await sessoes.iniciar_motorista(ct, body.rota_id or _rota_id(body.tripId))
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)
    return {"sessionId": sa.id, "agentId": sa.agent_id, "agentUid": sa.agent_uid, "appId": ct.settings.agora_app_id,
            "channel": sa.canal, "uid": sa.user_uid, "token": tokens.token_cliente(ct.settings, sa.canal, sa.user_uid),
            "status": sa.status, "tripId": str(sa.rota_id)}


@router.post("/agent/stop")
async def agent_stop(body: AgentStop, ct=Depends(c)):
    sid = body.sessionId
    if sid is None and body.agentId:
        with sessao() as s:
            sa = s.exec(select(SessaoAgente).where(SessaoAgente.agent_id == body.agentId)).first()
        sid = sa.id if sa else None
    if sid is None:
        raise erro_http(consultas.NaoEncontrado("sessão não existe"))
    try:
        sa = await sessoes.encerrar(ct, sid)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)
    return {"sessionId": sa.id, "status": sa.status}


class CallReceiver(BaseModel):
    tripId: Optional[str] = None
    reason: str = "cco_sem_resposta"  # ou "aproximacao"


@router.post("/call/receiver")
async def call_receiver(body: CallReceiver = CallReceiver(), ct=Depends(c)):
    rid = _rota_id(body.tripId)
    t = consultas.ultima_task(rid)
    try:
        lig = await ligacoes.ligar(ct, rid, body.reason, t.id if t else None)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)
    return {"callId": lig.id, "channel": lig.canal, "mode": lig.modo, "status": lig.status, "to": lig.numero,
            "receiverPage": f"/recebedor?ligacao={lig.id}" if lig.modo == "rtc" else None}


# ---------------- eventos (outbox) ----------------

@router.get("/events")
def get_events(tripId: Optional[str] = None, since: Optional[str] = Query(None, description="receivedAt ISO; devolve só os posteriores")):
    q = select(Evento).where(Evento.tipo != TipoEvento.EVENTO_APP).order_by(Evento.id)
    if tripId:
        q = q.where(Evento.rota_id == _rota_id(tripId))
    if since:
        q = q.where(Evento.timestamp > datetime.fromisoformat(since.rstrip("Z")))
    with sessao() as s:
        return [para_dominio(e) for e in s.exec(q).all()]


async def _aplicar(ct, rid: int, e: DomainEventIn) -> None:
    p = e.payload or {}
    if e.type == "ArrivalRegistered":
        await tasks.on_chegada(ct, rid, origem="app", transcricao=p.get("transcricao"))
    elif e.type == "PickupConfirmed":
        await tasks.confirmar_retirada(ct, rid, transcricao=p.get("transcricao"), origem="app")
    elif e.type == "OccurrenceCreated":
        tasks.registrar_ocorrencia(ct, rid, p.get("tipo", "outro"), p.get("descricao", ""), transcricao=p.get("transcricao"))
    elif e.type == "UnloadConfirmed":
        await tasks.confirmar_descarga(ct, rid, por="motorista (app)", transcricao=p.get("transcricao"))
    elif e.type == "ReportSubmitted":
        reportes.registrar(ct, rid, p.get("tipo", "checkin"), p.get("campos", {}), p.get("transcricao"))


@router.post("/events")
async def post_event(e: DomainEventIn, ct=Depends(c)):
    """Recebe o outbox do app. Idempotente por idempotencyKey: repetido devolve 409 (o app trata como enviado)."""
    rid = _rota_id(e.tripId)
    try:
        with sessao() as s:
            ev = Evento(rota_id=rid, tipo=TipoEvento.EVENTO_APP, mensagem=f"Evento do app: {e.type}",
                        idempotency_key=e.idempotencyKey, source=e.source,
                        dados={"type": e.type, "payload": e.payload, "occurredAt": e.occurredAt, "id": e.id})
            s.add(ev)
            s.commit()
            s.refresh(ev)
    except IntegrityError:
        return JSONResponse({"status": "duplicate", "idempotencyKey": e.idempotencyKey}, status_code=409)
    try:
        await _aplicar(ct, rid, e)
    except Exception as err:  # noqa: BLE001
        raise erro_http(err)
    return {"status": "accepted", "id": f"evt-{ev.id}", "idempotencyKey": e.idempotencyKey, "receivedAt": serial(ev.timestamp)}


# ---------------- dados mock da viagem ----------------

@router.get("/api/route")
def api_route(tripId: Optional[str] = None, driverId: Optional[int] = None):
    """Rota da viagem: por tripId, ou a rota atual atribuída ao motorista (driverId)."""
    if driverId is not None and not tripId:
        atual = publicacao.rota_atual(driverId)
        if not atual:
            raise erro_http(consultas.NaoEncontrado("motorista sem rota atribuída"))
        tripId = str(atual.id)
    try:
        r, nome, empresa = consultas.contexto_rota(_rota_id(tripId))
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)
    return {
        "tripId": str(r.id), "status": r.status, "company": empresa, "driver": {"name": nome},
        "plate": r.placa, "invoice": r.nota_fiscal, "cargo": r.carga_descricao, "weightT": r.carga_t,
        "unloadWindow": r.janela_descarga,
        "origin": {"name": r.origem_nome, "lat": r.origem_lat, "lng": r.origem_lng},
        "destination": {"name": r.destino_nome, "lat": r.destino_lat, "lng": r.destino_lng},
        "polyline": r.trajeto,
        "receiver": {"company": r.recebedor_empresa, "name": r.recebedor_nome, "phone": r.recebedor_telefone_e164},
        "driverId": r.motorista_id, "assignedAt": serial(r.atribuida_em) if r.atribuida_em else None,
        "position": {"lat": r.ultima_lat, "lng": r.ultima_lng, "distanceM": r.distancia_m, "etaMin": r.eta_min},
        "channel": sessoes.canal_motorista(r.id), "driverUid": sessoes.UID_MOTORISTA, "agentUid": sessoes.UID_AGENTE_MOTORISTA,
    }


@router.get("/api/receivers")
def api_receivers(ct=Depends(c)):
    return metricas.ranking_recebedores(ct)


@router.get("/api/metrics")
def api_metrics(ct=Depends(c)):
    return metricas.calcular(ct)


@router.get("/api/documents")
def api_documents(tripId: Optional[str] = None):
    """Documentos fictícios da viagem (mock declarado no README; leitura por voz é P2)."""
    from ..dominio import documentos

    r, _, empresa = consultas.contexto_rota(_rota_id(tripId))
    return documentos.da_rota(r, empresa)


class SsoIn(BaseModel):
    email: Optional[str] = None


@router.post("/auth/sso", response_model=SsoOut)
def auth_sso(body: SsoIn = SsoIn()):
    """Login mock: e-mail cadastrado seleciona um perfil persistido e recebe token fictício."""
    try:
        profile = usuarios.por_email(body.email if body.email is not None else "carlos@rotasul.test")
    except Exception as error:
        raise erro_http(error)
    return {"token": f"mock-{uuid.uuid4().hex}", "user": profile}
