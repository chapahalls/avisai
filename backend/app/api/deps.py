from fastapi import HTTPException

from ..infra import container as ct
from ..integracoes.agora_rest import AgoraErro
from ..integracoes.tokens import CredencialAgoraInvalida
from ..servicos.consultas import NaoEncontrado
from ..servicos.usuarios import ConflitoUsuario


def c() -> ct.Container:
    return ct.atual()


def erro_http(e: Exception) -> HTTPException:
    if isinstance(e, NaoEncontrado):
        return HTTPException(404, str(e))
    if isinstance(e, AgoraErro):
        return HTTPException(502, {"erro": "agora", "status": e.status, "corpo": e.corpo})
    if isinstance(e, CredencialAgoraInvalida):
        return HTTPException(500, str(e))
    if isinstance(e, ConflitoUsuario):
        return HTTPException(409, str(e))
    if isinstance(e, ValueError):
        return HTTPException(400, str(e))
    if isinstance(e, RuntimeError):
        return HTTPException(503, str(e))
    return HTTPException(500, str(e))
