"""Peça 5 e atalhos de demo: rotas, posição (GPS), chegada, descarga, reset."""
from fastapi import APIRouter, Depends
from sqlmodel import select

from ..infra.db import sessao
from ..infra.models import (Estadia, Evento, EventoGeo, LigacaoRecebedor, Motorista, Ocorrencia, Reporte, Rota,
                            SessaoAgente, SolicitacaoCentral, TaskCCO)
from ..servicos import central, consultas, rotas, sessoes, tasks
from .deps import c, erro_http
from .schemas import Descarga, NovaSolicitacao, Posicao, PosicaoOut

router = APIRouter(tags=["rotas"])


def rota_publica(r: Rota, com_trajeto: bool = False) -> dict:
    d = r.model_dump(exclude=None if com_trajeto else {"trajeto"})
    d.update(canal_motorista=sessoes.canal_motorista(r.id), uid_motorista=sessoes.UID_MOTORISTA,
             uid_cco=sessoes.UID_CCO, uid_agente=sessoes.UID_AGENTE_MOTORISTA)
    with sessao() as s:
        m = s.get(Motorista, r.motorista_id)
    d["motorista_nome"] = m.nome if m else None
    return d


@router.get("/rotas")
def listar():
    with sessao() as s:
        return [rota_publica(r) for r in s.exec(select(Rota)).all()]


@router.get("/rotas/{rota_id}")
def obter(rota_id: int):
    try:
        return rota_publica(consultas.rota(rota_id), com_trajeto=True)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)


@router.post("/rotas/{rota_id}/posicao", response_model=PosicaoOut)
async def posicao(rota_id: int, body: Posicao, ct=Depends(c)):
    """GPS do celular (fonte=celular, dispara as geocercas) ou do rastreador do caminhão (fonte=rastreador, prova)."""
    try:
        return await rotas.registrar_posicao(ct, rota_id, body.lat, body.lng, body.velocidade_kmh, body.precisao_m, body.fonte)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)


@router.post("/rotas/{rota_id}/chegada")
async def chegada(rota_id: int, ct=Depends(c)):
    """Chegada manual (atalho de demo). Idempotente."""
    try:
        return await tasks.on_chegada(ct, rota_id, origem="manual")
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)


@router.post("/rotas/{rota_id}/descarga")
async def descarga(rota_id: int, body: Descarga = Descarga(), ct=Depends(c)):
    """CCO confirma a descarga: encerra estadia e Task."""
    try:
        return await tasks.confirmar_descarga(ct, rota_id, por=body.por)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)


@router.post("/rotas/{rota_id}/reset")
async def reset(rota_id: int, ct=Depends(c)):
    """Volta a rota ao início para repetir a demo."""
    for t in list(ct.tarefas.values()):
        t.cancel()
    with sessao() as s:
        r = s.get(Rota, rota_id)
        if not r:
            raise erro_http(consultas.NaoEncontrado("rota não existe"))
        for modelo in (Evento, EventoGeo, Estadia, Ocorrencia, Reporte, SolicitacaoCentral):
            for x in s.exec(select(modelo).where(modelo.rota_id == rota_id)).all():
                s.delete(x)
        for x in s.exec(select(SessaoAgente).where(SessaoAgente.rota_id == rota_id, SessaoAgente.papel == "recebedor")).all():
            s.delete(x)
        s.commit()
        for modelo in (LigacaoRecebedor, TaskCCO):
            for x in s.exec(select(modelo).where(modelo.rota_id == rota_id)).all():
                s.delete(x)
            s.commit()
        r.status, r.ultima_lat, r.ultima_lng, r.distancia_m, r.eta_min = "planejada", None, None, None, None
        r.rastreador_lat = r.rastreador_lng = r.rastreador_em = None
        s.add(r)
        s.commit()
    ct.eventos.publicar("reset", {"rota_id": rota_id}, rota_id)
    return {"ok": True}


@router.post("/rotas/{rota_id}/solicitacoes")
async def nova_solicitacao(rota_id: int, body: NovaSolicitacao, ct=Depends(c)):
    """Pedido da central: o agente pergunta ao motorista e a resposta volta estruturada."""
    try:
        return await central.perguntar(ct, rota_id, body.pergunta)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)


@router.get("/rotas/{rota_id}/solicitacoes")
def solicitacoes(rota_id: int):
    return central.listar(rota_id)
