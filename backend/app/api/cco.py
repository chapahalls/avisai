"""Peça 8: painel do CCO (SSE), WS do app do motorista, Tasks e eventos."""
import asyncio
import json
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlmodel import select

from ..infra import container as ct_mod
from ..infra.db import sessao
from ..infra.eventos import dumps, envelope
from ..infra.models import Estadia, Evento, LigacaoRecebedor, Ocorrencia, Rota, TaskCCO
from ..servicos import consultas, tasks
from .deps import c, erro_http
from .rotas import rota_publica
from .schemas import Confirmar, EventoStream

router = APIRouter(tags=["cco"])


def snapshot(ct, rota_id: Optional[int] = None) -> dict:
    def q(modelo, limite=20):
        x = select(modelo).order_by(modelo.id.desc()).limit(limite)
        return x.where(modelo.rota_id == rota_id) if rota_id else x

    with sessao() as s:
        rotas = s.exec(select(Rota).where(Rota.id == rota_id) if rota_id else select(Rota)).all()
        return {
            "rotas": [rota_publica(r) for r in rotas],
            "tasks": [t.model_dump() for t in s.exec(q(TaskCCO)).all()],
            "estadias": [consultas.resumo_estadia_dict(ct, e) for e in s.exec(q(Estadia)).all()],
            "ligacoes": [l.model_dump() for l in s.exec(q(LigacaoRecebedor)).all()],
            "ocorrencias": [o.model_dump() for o in s.exec(q(Ocorrencia)).all()],
            "eventos": [envelope(e) for e in s.exec(q(Evento, 50)).all()],
        }


def _contador(ct, rota_id: Optional[int]) -> dict:
    with sessao() as s:
        q = select(Estadia).where(Estadia.fim == None)  # noqa: E711
        if rota_id:
            q = q.where(Estadia.rota_id == rota_id)
        return {"estadias": [consultas.resumo_estadia_dict(ct, e) for e in s.exec(q).all()]}


async def fluxo(ct, rota_id: Optional[int] = None, intervalo_contador: float = 1.0) -> AsyncIterator[tuple[str, dict]]:
    """Fonte comum do SSE e do WS: snapshot, depois eventos publicados e o contador da estadia."""
    a = ct.eventos.assinar(rota_id)
    try:
        yield "snapshot", json.loads(dumps(snapshot(ct, rota_id)))
        while True:
            try:
                tipo, msg = await asyncio.wait_for(a.fila.get(), timeout=intervalo_contador)
                yield tipo, json.loads(msg)
            except asyncio.TimeoutError:
                yield "contador", json.loads(dumps(_contador(ct, rota_id)))
    finally:
        ct.eventos.cancelar(a)


@router.get("/cco/estado")
def estado(rota_id: Optional[int] = None, ct=Depends(c)):
    return json.loads(dumps(snapshot(ct, rota_id)))


@router.get("/cco/stream")
async def stream(request: Request, rota_id: Optional[int] = None, ct=Depends(c)):
    """SSE. Eventos: snapshot, evento (EventoStream), task, posicao, fala, contador (1/s), reset."""
    async def gerar():
        async for tipo, dado in fluxo(ct, rota_id):
            if await request.is_disconnected():
                break
            yield f"event: {tipo}\ndata: {json.dumps(dado, ensure_ascii=False)}\n\n"

    return StreamingResponse(gerar(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.websocket("/ws")
async def ws(websocket: WebSocket, rota_id: Optional[int] = None):
    """WebSocket para o app RN: mesmas mensagens do SSE, como {"canal": tipo, "dado": {...}}."""
    await websocket.accept()
    ct = ct_mod.atual()
    try:
        async for tipo, dado in fluxo(ct, rota_id):
            await websocket.send_text(json.dumps({"canal": tipo, "dado": dado}, ensure_ascii=False))
    except WebSocketDisconnect:
        pass


@router.get("/tasks")
def listar_tasks():
    with sessao() as s:
        return s.exec(select(TaskCCO).order_by(TaskCCO.id.desc()).limit(50)).all()


@router.post("/tasks/{task_id}/confirmar")
async def confirmar(task_id: int, body: Confirmar = Confirmar(), ct=Depends(c)):
    """CCO assume a Task: para o escalonamento."""
    try:
        return await tasks.confirmar(ct, task_id, body.confirmado_por)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)


@router.get("/eventos", response_model=list[EventoStream])
def eventos(rota_id: Optional[int] = None, limite: int = 100):
    with sessao() as s:
        q = select(Evento).order_by(Evento.id.desc()).limit(limite)
        if rota_id:
            q = q.where(Evento.rota_id == rota_id)
        return [envelope(e) for e in s.exec(q).all()]
