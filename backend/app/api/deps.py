from typing import Optional

from fastapi import Depends, HTTPException, Request

from ..infra import auth
from ..infra import container as ct
from ..infra.db import sessao
from ..infra.models import Rota, SessaoAgente
from ..integracoes.livekit import LiveKitErro
from ..integracoes.nominatim import GeocodificacaoErro
from ..servicos.consultas import ConflitoEstado, NaoEncontrado
from ..servicos.usuarios import ConflitoUsuario


def c() -> ct.Container:
    return ct.atual()


def erro_http(e: Exception) -> HTTPException:
    if isinstance(e, NaoEncontrado):
        return HTTPException(404, str(e))
    if isinstance(e, GeocodificacaoErro):
        return HTTPException(502, {"erro": "geocodificacao", "detalhe": str(e)})
    if isinstance(e, LiveKitErro):
        return HTTPException(502, {"erro": "livekit", "status": e.status, "corpo": e.corpo})
    if isinstance(e, ConflitoUsuario | ConflitoEstado):
        return HTTPException(409, str(e))
    if isinstance(e, ValueError):
        return HTTPException(400, str(e))
    if isinstance(e, RuntimeError):
        return HTTPException(503, str(e))
    return HTTPException(500, str(e))


def _token_da_requisicao(request: Request) -> str:
    cabecalho = request.headers.get("authorization", "")
    if cabecalho.lower().startswith("bearer "):
        return cabecalho[7:].strip()
    # EventSource e WebSocket não mandam cabeçalho: aceitam ?token=
    return request.query_params.get("token", "")


def usuario_atual(request: Request, ct: ct.Container = Depends(c)) -> Optional[dict]:
    """Claims do token, ou None quando não há token. Token inválido é sempre 401."""
    token = _token_da_requisicao(request)
    if not token:
        return None
    try:
        return auth.validar(ct.settings, token)
    except auth.TokenInvalido:
        raise HTTPException(401, "token inválido ou expirado", headers={"WWW-Authenticate": "Bearer"})


def exigir_cco(request: Request, ct: ct.Container = Depends(c)) -> Optional[dict]:
    """Ações da central. Com AUTH_OBRIGATORIA=false (padrão da demo local), só valida o token se vier."""
    usuario = usuario_atual(request, ct)
    if not ct.settings.auth_obrigatoria:
        return usuario
    if usuario is None:
        raise HTTPException(401, "faça login como CCO (/auth/sso)", headers={"WWW-Authenticate": "Bearer"})
    if usuario.get("role") != "cco":
        raise HTTPException(403, "ação exclusiva da central (papel cco)")
    return usuario


def exigir_login(request: Request, ct: ct.Container = Depends(c)) -> Optional[dict]:
    """Qualquer papel logado. Com AUTH_OBRIGATORIA=false, só valida o token se vier."""
    usuario = usuario_atual(request, ct)
    if ct.settings.auth_obrigatoria and usuario is None:
        raise HTTPException(401, "faça login (/auth/sso)", headers={"WWW-Authenticate": "Bearer"})
    return usuario


def verificar_acesso_rota(ct: ct.Container, usuario: Optional[dict], rota_id: int) -> None:
    """A central acessa qualquer rota; o motorista, só a rota atribuída a ele (claim driverId)."""
    if not ct.settings.auth_obrigatoria or usuario is None:
        return
    papel = usuario.get("role")
    if papel == "cco":
        return
    if papel != "driver":
        raise HTTPException(403, "papel sem acesso a rotas")
    with sessao() as s:
        rota = s.get(Rota, rota_id)
    if rota is None:
        return  # o próprio endpoint responde 404
    if rota.motorista_id is None or rota.motorista_id != usuario.get("driverId"):
        raise HTTPException(403, "rota atribuída a outro motorista")


def exigir_acesso_rota(rota_id: int, request: Request, ct: ct.Container = Depends(c)) -> Optional[dict]:
    """Ações do motorista na própria rota (GPS, chegada, descarga, ligação, arquivos). A central também pode."""
    usuario = exigir_login(request, ct)
    verificar_acesso_rota(ct, usuario, rota_id)
    return usuario


def verificar_acesso_sessao(ct: ct.Container, usuario: Optional[dict], sessao_id: int) -> None:
    if not ct.settings.auth_obrigatoria or usuario is None:
        return
    with sessao() as s:
        sa = s.get(SessaoAgente, sessao_id)
    if sa is not None:
        verificar_acesso_rota(ct, usuario, sa.rota_id)


def exigir_acesso_sessao(sessao_id: int, request: Request, ct: ct.Container = Depends(c)) -> Optional[dict]:
    """Sessão de voz: vale o dono da rota da sessão, ou a central."""
    usuario = exigir_login(request, ct)
    verificar_acesso_sessao(ct, usuario, sessao_id)
    return usuario


def limitar_ligacao(ct: ct.Container, rota_id: int) -> None:
    s = ct.settings
    if not auth.limite_chamadas.permitir(f"rota:{rota_id}", s.ligacoes_manuais_max, s.ligacoes_manuais_janela_s):
        raise HTTPException(429, f"limite de {s.ligacoes_manuais_max} ligações manuais por rota a cada "
                                 f"{int(s.ligacoes_manuais_janela_s // 60)} min")
