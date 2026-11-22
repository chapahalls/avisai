"""Peça 7: ligação ao recebedor e página do plano B."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import select

from ..infra.db import sessao
from ..infra.models import LigacaoRecebedor
from ..integracoes import tokens
from ..servicos import consultas, ligacoes, sessoes
from .deps import c, erro_http
from .schemas import Ligar

router = APIRouter(tags=["recebedor"])
STATIC = Path(__file__).resolve().parents[2] / "static"


@router.post("/rotas/{rota_id}/ligar-recebedor")
async def ligar_recebedor(rota_id: int, body: Ligar = Ligar(), ct=Depends(c)):
    """Dispara a ligação ao recebedor na hora (atalho de demo)."""
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
    if lig.canal and ct.settings.agora_configurada():
        d.update(app_id=ct.settings.agora_app_id, uid=sessoes.UID_RECEBEDOR,
                 token=tokens.token_cliente(ct.settings, lig.canal, sessoes.UID_RECEBEDOR))
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


@router.get("/recebedor", include_in_schema=False)
def pagina_recebedor():
    """Plano B: o recebedor atende a ligação do agente por esta página."""
    return FileResponse(STATIC / "recebedor.html")


@router.get("/teste", include_in_schema=False)
def pagina_teste():
    """Cliente mínimo do motorista para testar o backend (o app real é do front)."""
    return FileResponse(STATIC / "motorista.html")
