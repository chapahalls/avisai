"""Falas gravadas sem sinal: o outbox do app entrega o áudio quando a rede volta."""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from ..infra.eventos import serial
from ..servicos import falas_offline
from .deps import c, erro_http

router = APIRouter(tags=["falas-offline"])


@router.post("/rotas/{rota_id}/falas-offline", status_code=201)
async def receber(rota_id: int, audio: UploadFile = File(...), idempotencyKey: str = Form(...),
                  faladoEm: Optional[str] = Form(None), duracaoMs: Optional[int] = Form(None, ge=0),
                  ct=Depends(c)):
    """Idempotente por idempotencyKey: repetido devolve 409 (o app trata como enviado).
    A transcrição e o agente rodam em segundo plano; a resposta chega como `aviso_motorista`."""
    try:
        ev, novo = await falas_offline.receber(ct, rota_id, idempotencyKey, faladoEm, duracaoMs, audio)
    except HTTPException:
        raise
    except Exception as error:
        raise erro_http(error)
    corpo = {"id": f"evt-{ev.id}", "idempotencyKey": idempotencyKey, "receivedAt": serial(ev.timestamp)}
    if not novo:
        return JSONResponse({"status": "duplicate", **corpo}, status_code=409)
    ct.em_segundo_plano(f"fala_offline:{ev.id}", falas_offline.processar(ct, ev.id))
    return {"status": "accepted", **corpo}
