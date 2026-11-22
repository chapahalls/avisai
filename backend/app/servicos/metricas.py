"""KPIs do dashboard do CCO (docs/arquitetura-avisai.md, seção 6.2) e ranking de recebedores."""
import statistics
from collections import defaultdict
from typing import Optional

from sqlmodel import select

from ..infra.db import sessao
from ..infra.models import Estadia, Evento, LigacaoRecebedor, Reporte, Rota, TaskCCO
from . import consultas


def _media(xs: list[float]) -> Optional[float]:
    return round(sum(xs) / len(xs), 2) if xs else None


def _pct(a: int, b: int) -> Optional[float]:
    return round(100 * a / b, 1) if b else None


def _avisados_antes(evs: list[Evento], rota_id: int) -> bool:
    chegada = next((e.id for e in evs if e.rota_id == rota_id and e.tipo == "chegada"), None)
    aviso = next((e.id for e in evs if e.rota_id == rota_id and e.tipo == "aviso_recebedor"), None)
    return aviso is not None and (chegada is None or aviso < chegada)


def calcular(c) -> dict:
    with sessao() as s:
        estadias = s.exec(select(Estadia)).all()
        tasks = s.exec(select(TaskCCO)).all()
        ligs = s.exec(select(LigacaoRecebedor)).all()
        reps = s.exec(select(Reporte).where(Reporte.completo == True)).all()  # noqa: E712
        evs = s.exec(select(Evento).order_by(Evento.id)).all()
    resumos = [consultas.resumo_estadia(c, e) for e in estadias]
    encerradas = [r for r in resumos if r.encerrada]
    rotas_chegada = {e.rota_id for e in evs if e.tipo == "chegada"}
    acoes = [(t.confirmado_em - t.criada_em).total_seconds() / 60 for t in tasks if t.confirmado_em]
    validas = [l for l in ligs if l.status != "falhou"]
    lat = sorted(c.latencias)
    return {
        "entregas": len(encerradas),
        "horas_paradas_media": _media([r.horas_paradas for r in encerradas]),
        "estadia_devida_total": round(sum(r.valor for r in resumos), 2),
        "tempo_ate_acao_cco_min_media": _media(acoes),
        "tasks_escaladas": sum(1 for e in evs if e.tipo == "escalada_recebedor"),
        "pct_recebedores_avisados": _pct(sum(1 for r in rotas_chegada if _avisados_antes(evs, r)), len(rotas_chegada)),
        "pct_ligacoes_atendidas": _pct(sum(1 for l in validas if l.atendida), len(validas)),
        "pct_reportes_completos_1a": _pct(sum(1 for r in reps if r.perguntas_complemento == 0), len(reps)),
        "contatos_resolvidos_pelo_agente": sum(1 for e in evs if e.tipo in ("resposta_recebedor", "relatorio", "resposta_central")),
        "latencia_voz_ms": {  # tempo do nosso LLM até o 1º trecho de resposta (não inclui ASR/TTS/RTC)
            "p50": round(statistics.median(lat)) if lat else None,
            "p95": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))]) if lat else None,
            "amostras": len(lat),
        },
    }


def ranking_recebedores(c) -> list[dict]:
    with sessao() as s:
        rotas = s.exec(select(Rota)).all()
        estadias = s.exec(select(Estadia)).all()
        ligs = s.exec(select(LigacaoRecebedor)).all()
        evs = s.exec(select(Evento).order_by(Evento.id)).all()
    por: dict[str, dict] = defaultdict(lambda: {"entregas": 0, "esperas": [], "ligacoes": 0, "atendidas": 0,
                                               "estadia_devida": 0.0, "avisados": 0})
    info = {}
    for r in rotas:
        d = por[r.recebedor_empresa]
        info[r.recebedor_empresa] = (r.recebedor_nome, r.recebedor_telefone_e164)
        for e in (x for x in estadias if x.rota_id == r.id):
            res = consultas.resumo_estadia(c, e)
            d["estadia_devida"] += res.valor
            if res.encerrada:
                d["entregas"] += 1
                d["esperas"].append(res.horas_paradas)
        for l in (x for x in ligs if x.rota_id == r.id and x.status != "falhou"):
            d["ligacoes"] += 1
            d["atendidas"] += int(l.atendida)
        d["avisados"] += int(_avisados_antes(evs, r.id))
    out = [{
        "recebedor": nome, "responsavel": info[nome][0], "telefone_e164": info[nome][1],
        "entregas": d["entregas"], "espera_media_h": _media(d["esperas"]),
        "ligacoes": d["ligacoes"], "ligacoes_atendidas": d["atendidas"],
        "estadia_devida": round(d["estadia_devida"], 2), "avisados_antes_da_chegada": d["avisados"],
    } for nome, d in por.items()]
    return sorted(out, key=lambda x: (x["espera_media_h"] or 0), reverse=True)
