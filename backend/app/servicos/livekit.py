"""Token de participante do LiveKit (JWT HS256 assinado com a chave da API do projeto).

Formato documentado pelo LiveKit: `iss` = API key, `sub` = identidade, grants em `video` e,
opcionalmente, despacho explícito de agente em `roomConfig.agents`.
"""
import re
import secrets
import time
from typing import Optional

import jwt

from ..infra.settings import Settings

SALA_VALIDA = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class LiveKitNaoConfigurado(RuntimeError):
    pass


def identidade_para(usuario: Optional[dict]) -> str:
    """Identidade estável para usuário logado; sem login (auth desligada), uma identidade de demo."""
    if usuario and usuario.get("sub"):
        return f"{usuario.get('role', 'user')}-{usuario['sub']}"
    return f"demo-{secrets.token_hex(4)}"


def sala_para(identidade: str, sala: Optional[str]) -> str:
    if sala is None or not sala.strip():
        return f"rodar-demo-{identidade}"
    sala = sala.strip()
    if not SALA_VALIDA.match(sala):
        raise ValueError("Sala inválida: use letras, números, _ ou - (até 64)")
    return sala


def token_participante(s: Settings, identidade: str, sala: str, nome: Optional[str] = None,
                       agora: Optional[float] = None) -> str:
    if not s.livekit_configurada():
        raise LiveKitNaoConfigurado("LiveKit não configurado (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)")
    t = int(agora if agora is not None else time.time())
    claims: dict = {
        "iss": s.livekit_api_key,
        "sub": identidade,
        "nbf": t,
        "exp": t + int(s.livekit_token_validade_min * 60),
        "name": nome or identidade,
        "video": {"room": sala, "roomJoin": True, "canPublish": True, "canSubscribe": True, "canPublishData": True},
    }
    if s.livekit_agent_name:
        claims["roomConfig"] = {"agents": [{"agentName": s.livekit_agent_name}]}
    return jwt.encode(claims, s.livekit_api_secret, algorithm="HS256")
