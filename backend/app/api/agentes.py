"""Peças 1 e 2: tokens e sessões do agente."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import select

from ..infra.db import sessao
from ..infra.models import SessaoAgente
from ..integracoes.livekit import token as token_livekit
from ..servicos import sessoes
from .deps import c, erro_http, exigir_acesso_sessao, exigir_login, verificar_acesso_rota
from .schemas import Fala, NovaSessao, SessaoOut, TokenOut

router = APIRouter(tags=["agentes"])


@router.get("/token", response_model=TokenOut)
def token(request: Request, room: str = Query(...), identity: str = Query(..., min_length=1, max_length=128),
          ct=Depends(c), usuario=Depends(exigir_login)):
    """Token LiveKit curto para um participante autorizado da sala."""
    with sessao() as db:
        sa = db.exec(select(SessaoAgente).where(SessaoAgente.canal == room,
                                                SessaoAgente.status == "ativa")).first()
    if not sa:
        raise HTTPException(404, "sala sem sessão ativa")
    monitor = identity == f"cco-monitor-{sa.id}"
    if identity != sessoes.identidade_usuario(sa) and not monitor:
        raise HTTPException(403, "identidade não autorizada nesta sala")
    if monitor:
        if ct.settings.auth_obrigatoria and (usuario is None or usuario.get("role") != "cco"):
            raise HTTPException(403, "monitor exclusivo da central (papel cco)")
    else:
        verificar_acesso_rota(ct, usuario, sa.rota_id)
    try:
        t = token_livekit(ct.settings, room, identity, publish=not monitor,
                          publish_data=False, ttl=3600)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)
    return TokenOut(url=ct.settings.livekit_url, room=room, identity=identity, token=t)


def _publica(ct, sa: SessaoAgente) -> SessaoOut:
    d = sa.model_dump()
    d["livekit_url"] = ct.settings.livekit_url or None
    d["identity"] = sessoes.identidade_usuario(sa)
    d["token"] = sessoes.token_usuario(ct, sa) if ct.settings.livekit_configurada() else None
    return SessaoOut(**d)


@router.post("/sessions", response_model=SessaoOut)
async def criar_sessao(body: NovaSessao, ct=Depends(c), usuario=Depends(exigir_login)):
    """Despacha o agente LiveKit e devolve sala, identidade e token do motorista."""
    verificar_acesso_rota(ct, usuario, body.rota_id)
    try:
        sa = await sessoes.iniciar_motorista(ct, body.rota_id)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)
    return _publica(ct, sa)


@router.get("/sessions", response_model=list[SessaoOut])
def listar_sessoes():
    with sessao() as s:
        return [SessaoOut(**x.model_dump()) for x in s.exec(select(SessaoAgente).order_by(SessaoAgente.id.desc()).limit(50)).all()]


@router.delete("/sessions/{sessao_id}", response_model=SessaoOut, dependencies=[Depends(exigir_acesso_sessao)])
async def encerrar_sessao(sessao_id: int, ct=Depends(c)):
    try:
        return SessaoOut(**(await sessoes.encerrar(ct, sessao_id)).model_dump())
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)


@router.post("/sessions/{sessao_id}/speak", dependencies=[Depends(exigir_acesso_sessao)])
async def falar(sessao_id: int, body: Fala, ct=Depends(c)):
    """Fala proativa manual (teste). Os avisos automáticos usam o mesmo canal LiveKit."""
    try:
        await sessoes.falar(ct, sessao_id, body.texto, body.prioridade)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)
    return {"ok": True}
