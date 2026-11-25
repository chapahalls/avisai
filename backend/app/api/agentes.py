"""Peças 1 e 2: tokens e sessões do agente."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select

from ..infra.db import sessao
from ..infra.models import SessaoAgente
from ..integracoes import tokens
from ..servicos import sessoes
from .deps import c, erro_http, exigir_acesso_sessao, exigir_login, verificar_acesso_rota
from .schemas import Fala, NovaSessao, SessaoOut, TokenOut

router = APIRouter(tags=["agentes"])


@router.get("/token", response_model=TokenOut)
def token(channel: str = Query(...), uid: int = Query(...), ct=Depends(c), usuario=Depends(exigir_login)):
    """Token RTC+RTM (AccessToken2, 24h) para motorista, CCO ou recebedor. O motorista só pede o canal da própria rota."""
    if uid <= 0:
        raise HTTPException(400, "uid deve ser > 0")
    if ct.settings.auth_obrigatoria and usuario and usuario.get("role") != "cco":
        prefixo = sessoes.canal_motorista(0)[:-1]
        rota_do_canal = channel.removeprefix(prefixo)
        if not (channel.startswith(prefixo) and rota_do_canal.isdigit()):
            raise HTTPException(403, "canal fora da rota do motorista")
        verificar_acesso_rota(ct, usuario, int(rota_do_canal))
    try:
        t = tokens.token_cliente(ct.settings, channel, uid)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)
    return TokenOut(app_id=ct.settings.agora_app_id, channel=channel, uid=uid, token=t)


def _publica(ct, sa: SessaoAgente) -> SessaoOut:
    d = sa.model_dump()
    d["app_id"] = ct.settings.agora_app_id
    d["token"] = tokens.token_cliente(ct.settings, sa.canal, sa.user_uid) if ct.settings.agora_configurada() else None
    return SessaoOut(**d)


@router.post("/sessions", response_model=SessaoOut)
async def criar_sessao(body: NovaSessao, ct=Depends(c), usuario=Depends(exigir_login)):
    """Inicia o agente ConvoAI no canal do motorista. Devolve canal, uid e token do motorista."""
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
    """Fala proativa manual (teste). O fluxo automático usa o mesmo /speak da Agora."""
    try:
        await sessoes.falar(ct, sessao_id, body.texto, body.prioridade)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)
    return {"ok": True}
