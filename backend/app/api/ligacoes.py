"""Peça 7: ligação ao recebedor e página do plano B."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import select

from ..infra.db import sessao
from ..infra.models import ChamadaAgente, LigacaoRecebedor, SessaoAgente
from ..integracoes.livekit import token as token_livekit
from ..servicos import chamadas_agente, consultas, ligacoes, sessoes
from .deps import c, erro_http, exigir_acesso_rota, exigir_cco, limitar_ligacao
from .schemas import Ligar

router = APIRouter(tags=["recebedor"])
STATIC = Path(__file__).resolve().parents[2] / "static"


@router.post("/rotas/{rota_id}/ligar-recebedor", dependencies=[Depends(exigir_acesso_rota)])
async def ligar_recebedor(rota_id: int, body: Ligar = Ligar(), ct=Depends(c)):
    """Dispara a ligação ao recebedor na hora (atalho de demo)."""
    limitar_ligacao(ct, rota_id)
    t = consultas.ultima_task(rota_id)
    try:
        return await ligacoes.ligar(ct, rota_id, body.motivo, t.id if t else None)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)


@router.get("/ligacoes")
def listar():
    with sessao() as s:
        return s.exec(select(LigacaoRecebedor).order_by(LigacaoRecebedor.id.desc()).limit(50)).all()


def _com_token(ct, lig: LigacaoRecebedor) -> dict:
    d = lig.model_dump()
    if lig.canal and ct.settings.livekit_configurada() and lig.sessao_id:
        with sessao() as db:
            sa = db.get(SessaoAgente, lig.sessao_id)
        if sa:
            d.update(url=ct.settings.livekit_url, room=lig.canal,
                     identity=sessoes.identidade_usuario(sa), token=sessoes.token_usuario(ct, sa))
    return d


def _operador_publico(ct, chamada: ChamadaAgente) -> dict:
    d = chamada.model_dump()
    if chamada.livekit_room and ct.settings.livekit_configurada():
        identity = f"operador-{chamada.id}"
        d.update(
            url=ct.settings.livekit_url,
            room=chamada.livekit_room,
            identity=identity,
            token=token_livekit(ct.settings, chamada.livekit_room, identity, name="operador"),
        )
    return d


@router.get("/ligacoes/atual/recebedor")
def atual(ct=Depends(c)):
    """Ligação em andamento mais recente (a página /recebedor consulta a cada 2 s)."""
    with sessao() as s:
        lig = s.exec(select(LigacaoRecebedor).where(LigacaoRecebedor.status == "em_andamento")
                     .order_by(LigacaoRecebedor.id.desc())).first()
    return _com_token(ct, lig) if lig else {"ligacao": None}


@router.get("/ligacoes/{ligacao_id}")
def obter(ligacao_id: int, ct=Depends(c)):
    with sessao() as s:
        lig = s.get(LigacaoRecebedor, ligacao_id)
    if not lig:
        raise HTTPException(404, "ligação não existe")
    return _com_token(ct, lig)


@router.get("/operador/chamadas/atual")
def chamada_operador_atual(ct=Depends(c)):
    """A página /operador consulta a chamada RTC pendente e recebe somente o token dela."""
    with sessao() as s:
        chamada = s.exec(
            select(ChamadaAgente).where(ChamadaAgente.status == "livekit_tocando")
            .order_by(ChamadaAgente.id.desc())
        ).first()
    return {"chamada": _operador_publico(ct, chamada) if chamada else None}


@router.post("/operador/chamadas/{chamada_id}/atender", dependencies=[Depends(exigir_cco)])
async def atender_chamada_operador(chamada_id: int, ct=Depends(c)):
    try:
        return (await chamadas_agente.atender(ct, chamada_id)).model_dump()
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)


@router.get("/recebedor", include_in_schema=False)
def pagina_recebedor():
    """Plano B: o recebedor atende a ligação do agente por esta página."""
    return FileResponse(STATIC / "recebedor.html")


@router.get("/teste", include_in_schema=False)
def pagina_teste():
    """Cliente mínimo do motorista para testar o backend (o app real é do front)."""
    return FileResponse(STATIC / "motorista.html")
