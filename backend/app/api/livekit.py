"""Porta de entrada do teste ao vivo por LiveKit: estado da configuração e token curto de participante."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..servicos import livekit
from .deps import c, erro_http, exigir_login

router = APIRouter(tags=["livekit"])


class LiveKitConfigOut(BaseModel):
    configurado: bool
    url: Optional[str]
    agente: Optional[str]


class NovoTokenLiveKit(BaseModel):
    sala: Optional[str] = None


class LiveKitTokenOut(BaseModel):
    url: str
    token: str
    sala: str
    identidade: str


@router.get("/livekit/config", response_model=LiveKitConfigOut)
def config(ct=Depends(c)):
    """Público: diz se há LiveKit e qual URL usar. Nunca expõe chave ou segredo."""
    s = ct.settings
    return LiveKitConfigOut(configurado=s.livekit_configurada(), url=s.livekit_url or None, agente=s.livekit_agent_name or None)


@router.post("/livekit/token", response_model=LiveKitTokenOut)
def token(body: NovoTokenLiveKit, ct=Depends(c), usuario=Depends(exigir_login)):
    """Token de participante (padrão 60 min) para a sala pedida ou uma sala própria da identidade."""
    s = ct.settings
    if not s.livekit_configurada():
        raise HTTPException(503, "LiveKit não configurado no backend")
    try:
        identidade = livekit.identidade_para(usuario)
        sala = livekit.sala_para(identidade, body.sala)
        jwt_token = livekit.token_participante(s, identidade, sala, nome=(usuario or {}).get("email"))
    except Exception as error:  # noqa: BLE001
        raise erro_http(error)
    return LiveKitTokenOut(url=s.livekit_url, token=jwt_token, sala=sala, identidade=identidade)
