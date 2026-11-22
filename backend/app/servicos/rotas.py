"""Peça 5: posição do caminhão (GPS simulado na demo) e geocercas."""
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


async def registrar_posicao(c, rota_id: int, lat: float, lng: float, velocidade_kmh: Optional[float] = None,
                            precisao_m: Optional[float] = None) -> dict:
    vel = velocidade_kmh if velocidade_kmh and velocidade_kmh > 1 else c.settings.velocidade_padrao_kmh
    agora = c.relogio.agora()
    disparos = []
    with sessao() as s:
        r = s.get(Rota, rota_id)
        if not r:
            raise consultas.NaoEncontrado(f"rota {rota_id} não existe")
        x = geocerca.avaliar(lat, lng, (r.destino_lat, r.destino_lng), vel, r.aproximacao_min, r.raio_chegada_m)
        r.ultima_lat, r.ultima_lng, r.ultima_posicao_em = lat, lng, agora
        r.distancia_m, r.eta_min = x.distancia_m, x.eta_min
        if r.status == StatusRota.PLANEJADA:
            r.status = StatusRota.EM_TRANSITO
        if x.aproximou and not _ja_teve(s, rota_id, TipoGeo.APROXIMACAO):
            s.add(EventoGeo(rota_id=rota_id, tipo=TipoGeo.APROXIMACAO, lat=lat, lng=lng, precisao_m=precisao_m,
                            distancia_m=x.distancia_m, status="validado", timestamp=agora))
            r.status = StatusRota.APROXIMANDO
            disparos.append(TipoGeo.APROXIMACAO)
        if x.chegou and not _ja_teve(s, rota_id, TipoGeo.CHEGADA):
            s.add(EventoGeo(rota_id=rota_id, tipo=TipoGeo.CHEGADA, lat=lat, lng=lng, precisao_m=precisao_m,
                            distancia_m=x.distancia_m, timestamp=agora))
            r.status = StatusRota.NO_DESTINO
            disparos.append(TipoGeo.CHEGADA)
        s.add(r)
        s.commit()
        s.refresh(r)
    c.eventos.publicar("posicao", {"rota_id": rota_id, "lat": lat, "lng": lng, "distancia_m": r.distancia_m,
                                   "eta_min": r.eta_min, "status": r.status}, rota_id)
    if TipoGeo.APROXIMACAO in disparos:
        await on_aproximacao(c, r)
    if TipoGeo.CHEGADA in disparos:
        await tasks.on_chegada(c, rota_id, origem="gps")
    return {"rota_id": rota_id, "distancia_m": r.distancia_m, "eta_min": r.eta_min,
            "status": consultas.rota(rota_id).status, "disparos": [str(d) for d in disparos]}


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
