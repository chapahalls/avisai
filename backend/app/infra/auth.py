"""Token de acesso (JWT HS256) e limite de chamadas manuais.

O login continua simulado (perfis do seed, sem senha), mas o token é real:
assinado, com papel e validade. Com AUTH_OBRIGATORIA=true, as ações da central
exigem papel "cco".
"""
import logging
import secrets
import time
from collections import defaultdict, deque
from typing import Optional

import jwt

from .settings import Settings

log = logging.getLogger("avisai.auth")
ALGORITMO = "HS256"
EMISSOR = "rodar-backend"
_segredo_efemero: Optional[str] = None


class TokenInvalido(Exception):
    pass


def _segredo(s: Settings) -> str:
    global _segredo_efemero
    if s.auth_segredo:
        return s.auth_segredo
    if _segredo_efemero is None:
        _segredo_efemero = secrets.token_urlsafe(32)
        log.warning("AUTH_SEGREDO vazio: tokens assinados com segredo temporário (perdem validade ao reiniciar)")
    return _segredo_efemero


def emitir(s: Settings, perfil: dict, agora: Optional[float] = None) -> str:
    t = int(agora if agora is not None else time.time())
    claims = {
        "iss": EMISSOR,
        "sub": str(perfil["id"]),
        "email": perfil["email"],
        "role": perfil["role"],
        "driverId": perfil.get("driverId"),
        "iat": t,
        "exp": t + int(s.auth_token_validade_h * 3600),
    }
    return jwt.encode(claims, _segredo(s), algorithm=ALGORITMO)


def validar(s: Settings, token: str) -> dict:
    try:
        return jwt.decode(token, _segredo(s), algorithms=[ALGORITMO], issuer=EMISSOR,
                          options={"require": ["exp", "iat", "sub", "iss"]})
    except jwt.PyJWTError as e:
        raise TokenInvalido(str(e)) from e


class LimiteChamadas:
    """Janela deslizante em memória por chave (ex.: rota). Ligações custam dinheiro."""

    def __init__(self) -> None:
        self._marcas: dict[str, deque[float]] = defaultdict(deque)

    def permitir(self, chave: str, maximo: int, janela_s: float, agora: Optional[float] = None) -> bool:
        if maximo <= 0:
            return True
        t = agora if agora is not None else time.monotonic()
        fila = self._marcas[chave]
        while fila and t - fila[0] >= janela_s:
            fila.popleft()
        if len(fila) >= maximo:
            return False
        fila.append(t)
        return True

    def limpar(self) -> None:
        self._marcas.clear()


limite_chamadas = LimiteChamadas()
