"""Peça 5 e atalhos de demo: rotas, posição (GPS), chegada, descarga, reset."""
from fastapi import APIRouter, Depends
from sqlmodel import select

from ..infra.db import sessao
from ..infra.models import (ChamadaAgente, ChamadoCCO, Estadia, Evento, EventoGeo, LigacaoRecebedor, MensagemMotorista,
                            Motorista, Ocorrencia, Reporte, Rota, SessaoAgente, SolicitacaoCentral, TaskCCO)
from ..servicos import central, consultas, mensagens, publicacao, rotas, sessoes, tasks
from .deps import c, erro_http, exigir_acesso_rota, exigir_cco
from .schemas import Atribuir, Cancelar, Descarga, NovaMensagemMotorista, NovaRota, NovaSolicitacao, NovoMotorista, Posicao, PosicaoOut

router = APIRouter(tags=["rotas"])


def rota_publica(r: Rota, com_trajeto: bool = False) -> dict:
    d = r.model_dump(exclude=None if com_trajeto else {"trajeto"})
    d.update(canal_motorista=sessoes.canal_motorista(r.id))
    with sessao() as s:
        m = s.get(Motorista, r.motorista_id) if r.motorista_id else None
    d["motorista_nome"] = m.nome if m else None
    return d


@router.get("/rotas")
def listar():
    # order_by: sem isso a ordem do Postgres não é garantida e muda depois de um UPDATE (toda troca de
    # status de rota) — o smoke do deploy (ci.yml) e scripts/validar_fluxos.py dependem de `[0]` ser
    # sempre a mesma rota (a do seed, com nfe_chave; alerta do júri, score.md 2026-11-27).
    with sessao() as s:
        return [rota_publica(r) for r in s.exec(select(Rota).order_by(Rota.id)).all()]


@router.get("/rotas/{rota_id}")
def obter(rota_id: int):
    try:
        return rota_publica(consultas.rota(rota_id), com_trajeto=True)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)


@router.post("/rotas/{rota_id}/posicao", response_model=PosicaoOut, dependencies=[Depends(exigir_acesso_rota)])
async def posicao(rota_id: int, body: Posicao, ct=Depends(c)):
    """GPS do celular (fonte=celular, dispara as geocercas) ou do rastreador do caminhão (fonte=rastreador, prova)."""
    try:
        return await rotas.registrar_posicao(ct, rota_id, body.lat, body.lng, body.velocidade_kmh, body.precisao_m, body.fonte)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)


@router.post("/rotas/{rota_id}/chegada", dependencies=[Depends(exigir_acesso_rota)])
async def chegada(rota_id: int, ct=Depends(c)):
    """Chegada manual (atalho de demo). Idempotente."""
    try:
        return await tasks.on_chegada(ct, rota_id, origem="manual")
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)


@router.post("/rotas/{rota_id}/descarga", dependencies=[Depends(exigir_acesso_rota)])
async def descarga(rota_id: int, body: Descarga = Descarga(), ct=Depends(c)):
    """CCO confirma a descarga: encerra estadia e Task."""
    try:
        return await tasks.confirmar_descarga(ct, rota_id, por=body.por)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)


@router.post("/rotas/{rota_id}/reset", dependencies=[Depends(exigir_acesso_rota)])
async def reset(rota_id: int, ct=Depends(c)):
    """Volta a rota ao início para repetir a demo."""
    for t in list(ct.tarefas.values()):
        t.cancel()
    with sessao() as s:
        r = s.get(Rota, rota_id)
        if not r:
            raise erro_http(consultas.NaoEncontrado("rota não existe"))
        # Chamados apontam para ocorrências: saem antes, senão a chave estrangeira barra o reset.
        for x in s.exec(select(ChamadoCCO).where(ChamadoCCO.rota_id == rota_id)).all():
            s.delete(x)
        s.commit()
        for modelo in (Evento, EventoGeo, Estadia, Ocorrencia, Reporte, SolicitacaoCentral,
                       MensagemMotorista, ChamadaAgente):
            for x in s.exec(select(modelo).where(modelo.rota_id == rota_id)).all():
                s.delete(x)
        for x in s.exec(select(SessaoAgente).where(SessaoAgente.rota_id == rota_id,
                                                   SessaoAgente.papel.in_(("recebedor", "operador")))).all():
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


@router.post("/rotas/{rota_id}/solicitacoes", dependencies=[Depends(exigir_cco)])
async def nova_solicitacao(rota_id: int, body: NovaSolicitacao, ct=Depends(c)):
    """Pedido da central: o agente pergunta ao motorista e a resposta volta estruturada."""
    try:
        return await central.perguntar(ct, rota_id, body.pergunta)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)


@router.get("/rotas/{rota_id}/solicitacoes")
def solicitacoes(rota_id: int):
    return central.listar(rota_id)


@router.get("/rotas/{rota_id}/mensagens")
def mensagens_motorista(rota_id: int):
    return [x.model_dump() for x in mensagens.listar(rota_id)]


@router.post("/rotas/{rota_id}/mensagens", dependencies=[Depends(exigir_cco)])
async def enviar_mensagem_motorista(rota_id: int, body: NovaMensagemMotorista, ct=Depends(c)):
    """Ação da CCO: a mesma função exposta ao LLM fala e audita a mensagem."""
    try:
        return (await mensagens.falar_motorista(ct, rota_id, body.remetente, body.texto)).model_dump()
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)


@router.get("/rotas/{rota_id}/chamados")
def chamados_da_rota(rota_id: int):
    from ..servicos import chamados

    return [x.model_dump() for x in chamados.listar(rota_id)]


# ---------------- publicação de rota e motoristas (CCO) ----------------

@router.post("/rotas", dependencies=[Depends(exigir_cco)])
async def publicar_rota(body: NovaRota, ct=Depends(c)):
    """Transportadora publica a rota (trajeto simulado) e, se vier motorista_id, já atribui."""
    try:
        r = await publicacao.publicar(ct, body.model_dump(), body.motorista_id)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)
    return rota_publica(consultas.rota(r.id), com_trajeto=True)


@router.post("/rotas/{rota_id}/atribuir", dependencies=[Depends(exigir_cco)])
async def atribuir_rota(rota_id: int, body: Atribuir, ct=Depends(c)):
    """Atribui a rota a um motorista: gera RouteAssigned e o app (WS ?motorista_id=) recebe na hora."""
    try:
        r = await publicacao.atribuir(ct, rota_id, body.motorista_id)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)
    return rota_publica(r)


@router.post("/rotas/{rota_id}/cancelar", dependencies=[Depends(exigir_cco)])
async def cancelar_rota(rota_id: int, body: Cancelar, ct=Depends(c)):
    """Cancela a viagem antes da chegada ao destino. 409 quando já chegou, foi descarregada ou cancelada."""
    try:
        r = await publicacao.cancelar(ct, rota_id, body.motivo, body.por)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)
    return rota_publica(r)


@router.get("/motoristas")
def listar_motoristas():
    return publicacao.motoristas()


@router.post("/motoristas", dependencies=[Depends(exigir_cco)])
def criar_motorista(body: NovoMotorista):
    try:
        return publicacao.criar_motorista(body.nome, body.telefone_e164, body.email, body.empresa_id)
    except Exception as error:
        raise erro_http(error)


@router.get("/motoristas/{motorista_id}/rota-atual")
def rota_atual(motorista_id: int):
    r = publicacao.rota_atual(motorista_id)
    if not r:
        raise erro_http(consultas.NaoEncontrado("motorista sem rota atribuída"))
    return rota_publica(r, com_trajeto=True)
