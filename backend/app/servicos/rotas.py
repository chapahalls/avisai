"""Peça 5: posição (GPS do celular + rastreador do caminhão, simulados na demo) e geocercas.

Geocercas: origem (retirada), aproximação (ETA) e destino (chegada). Cada EventoGeo guarda as duas
posições; se celular e rastreador divergirem além do limite, o evento fica nao_validado e o CCO é alertado.
"""
from typing import Optional

from sqlmodel import select

from ..dominio import geocerca
from ..dominio.enums import StatusRota, TipoEvento, TipoGeo
from ..infra.db import sessao
from ..infra.models import EventoGeo, Rota
from . import consultas, ligacoes, tasks
from .sessoes import VozAgora


def _ja_teve(s, rota_id: int, tipo: str) -> bool:
    return s.exec(select(EventoGeo).where(EventoGeo.rota_id == rota_id, EventoGeo.tipo == tipo)).first() is not None


def prova(c, r: Rota, lat: float, lng: float) -> dict:
    """Campos de prova de um EventoGeo: posição do caminhão, divergência e status inicial."""
    if r.rastreador_lat is None:
        return {"caminhao_lat": None, "caminhao_lng": None, "divergencia_m": None, "status": "nao_validado"}
    div = round(geocerca.distancia_m(lat, lng, r.rastreador_lat, r.rastreador_lng))
    ok = div <= c.settings.divergencia_gps_max_m
    return {"caminhao_lat": r.rastreador_lat, "caminhao_lng": r.rastreador_lng, "divergencia_m": div,
            "status": "validado" if ok else "nao_validado"}


async def registrar_posicao(c, rota_id: int, lat: float, lng: float, velocidade_kmh: Optional[float] = None,
                            precisao_m: Optional[float] = None, fonte: str = "celular") -> dict:
    agora = c.relogio.agora()
    if fonte == "rastreador":
        with sessao() as s:
            r = s.get(Rota, rota_id)
            if not r:
                raise consultas.NaoEncontrado(f"rota {rota_id} não existe")
            r.rastreador_lat, r.rastreador_lng, r.rastreador_em = lat, lng, agora
            s.add(r)
            s.commit()
            s.refresh(r)
        c.eventos.publicar("posicao", {"rota_id": rota_id, "fonte": "rastreador", "lat": lat, "lng": lng}, rota_id)
        return {"rota_id": rota_id, "distancia_m": r.distancia_m or 0, "eta_min": r.eta_min or 0,
                "status": r.status, "disparos": []}

    vel = velocidade_kmh if velocidade_kmh and velocidade_kmh > 1 else c.settings.velocidade_padrao_kmh
    disparos: list[str] = []
    divergentes: list[tuple[str, dict]] = []
    with sessao() as s:
        r = s.get(Rota, rota_id)
        if not r:
            raise consultas.NaoEncontrado(f"rota {rota_id} não existe")
        x = geocerca.avaliar(lat, lng, (r.destino_lat, r.destino_lng), vel, r.aproximacao_min, r.raio_chegada_m)
        na_origem = geocerca.distancia_m(lat, lng, r.origem_lat, r.origem_lng) <= r.raio_origem_m
        r.ultima_lat, r.ultima_lng, r.ultima_posicao_em = lat, lng, agora
        r.distancia_m, r.eta_min = x.distancia_m, x.eta_min

        if na_origem and not _ja_teve(s, rota_id, TipoGeo.RETIRADA):
            p = prova(c, r, lat, lng)
            s.add(EventoGeo(rota_id=rota_id, tipo=TipoGeo.RETIRADA, lat=lat, lng=lng, precisao_m=precisao_m,
                            timestamp=agora, **{**p, "status": "nao_validado"}))  # valida com a voz
            r.status = StatusRota.NA_ORIGEM
            disparos.append(TipoGeo.RETIRADA)
            if p["divergencia_m"] is not None and p["status"] == "nao_validado":
                divergentes.append((TipoGeo.RETIRADA, p))
        elif not na_origem and r.status in (StatusRota.PLANEJADA, StatusRota.NA_ORIGEM):
            r.status = StatusRota.EM_TRANSITO

        if x.aproximou and not _ja_teve(s, rota_id, TipoGeo.APROXIMACAO):
            s.add(EventoGeo(rota_id=rota_id, tipo=TipoGeo.APROXIMACAO, lat=lat, lng=lng, precisao_m=precisao_m,
                            distancia_m=x.distancia_m, status="validado", timestamp=agora))
            r.status = StatusRota.APROXIMANDO
            disparos.append(TipoGeo.APROXIMACAO)
        if x.chegou and not _ja_teve(s, rota_id, TipoGeo.CHEGADA):
            p = prova(c, r, lat, lng)
            s.add(EventoGeo(rota_id=rota_id, tipo=TipoGeo.CHEGADA, lat=lat, lng=lng, precisao_m=precisao_m,
                            distancia_m=x.distancia_m, timestamp=agora,
                            **{**p, "status": "nao_validado"}))  # valida com a confirmação por voz
            r.status = StatusRota.NO_DESTINO
            disparos.append(TipoGeo.CHEGADA)
            if p["status"] == "nao_validado" and p["divergencia_m"] is not None:
                divergentes.append((TipoGeo.CHEGADA, p))
        s.add(r)
        s.commit()
        s.refresh(r)

    c.eventos.publicar("posicao", {"rota_id": rota_id, "fonte": "celular", "lat": lat, "lng": lng,
                                   "distancia_m": r.distancia_m, "eta_min": r.eta_min, "status": r.status}, rota_id)
    for tipo, p in divergentes:
        c.eventos.registrar(
            TipoEvento.DIVERGENCIA_GPS,
            f"{tipo}: GPS do celular e rastreador do caminhão a {int(p['divergencia_m'])} m um do outro. Evento não validado.",
            rota_id, tipo_geo=str(tipo), divergencia_m=p["divergencia_m"],
        )
    if TipoGeo.RETIRADA in disparos:
        await on_origem(c, r)
    if TipoGeo.APROXIMACAO in disparos:
        await on_aproximacao(c, r)
    if TipoGeo.CHEGADA in disparos:
        await tasks.on_chegada(c, rota_id, origem="gps")
    return {"rota_id": rota_id, "distancia_m": r.distancia_m, "eta_min": r.eta_min,
            "status": consultas.rota(rota_id).status, "disparos": [str(d) for d in disparos]}


async def on_origem(c, r: Rota) -> None:
    c.eventos.registrar(TipoEvento.RETIRADA_DETECTADA, f"Caminhão {r.placa} na origem ({r.origem_nome}). Aguardando confirmação da retirada.", r.id)
    await VozAgora(c).falar_motorista(r.id, f"Você tá em {r.origem_nome}. Confirma a retirada da carga?")


async def on_aproximacao(c, r: Rota) -> None:
    eta = int(r.eta_min or 0)
    c.eventos.registrar(TipoEvento.APROXIMACAO, f"Caminhão {r.placa} a {eta} min de {r.destino_nome}. CCO avisado.",
                        r.id, eta_min=r.eta_min, distancia_m=r.distancia_m)
    voz = VozAgora(c)
    if c.settings.ligar_recebedor_na_aproximacao:
        await voz.falar_motorista(r.id, f"Faltam uns {eta} minutos. Já avisei o CCO e tô ligando pro recebimento pra confirmar a doca.")
        c.em_segundo_plano(f"lig-aprox-{r.id}", ligacoes.ligar(c, r.id, motivo="aproximacao"))
    else:
        await voz.falar_motorista(r.id, f"Faltam uns {eta} minutos pra {r.destino_nome}. Já avisei o CCO que você tá chegando.")
