"""Peça 3: conversa do LLM próprio. Estado vivo + ferramentas + streaming do texto final."""
import json
import logging
import time
from typing import AsyncIterator, Optional

from sqlmodel import select

from ..dominio import contingencia, prompts
from ..dominio.enums import Papel, TipoEvento
from ..infra.db import sessao
from ..infra.models import Evento, LigacaoRecebedor, SessaoAgente
from . import alertas, central, consultas, ferramentas, mensagens, reportes

log = logging.getLogger("avisai.conversa")
MAX_PASSADAS = 4


def limpar(msgs: list[dict]) -> list[dict]:
    """Tira os campos extras (turn_id, timestamp) que a Agora inclui com vendor=custom."""
    out = []
    for m in msgs:
        n = {k: m[k] for k in ("role", "content", "tool_calls", "tool_call_id", "name") if m.get(k) is not None}
        if n.get("role") == "assistant" and "content" not in n and "tool_calls" not in n:
            n["content"] = ""
        out.append(n)
    return out


def ultima_fala(msgs: list[dict]) -> str:
    for m in reversed(msgs):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, list):
                return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
            return c or ""
    return ""


def estado(c, rota_id: int) -> str:
    r = consultas.rota(rota_id)
    e = consultas.ultima_estadia(rota_id)
    with sessao() as s:
        evs = s.exec(select(Evento).where(Evento.rota_id == rota_id).order_by(Evento.id.desc()).limit(6)).all()
    return prompts.estado_atual(
        r.status, r.distancia_m, r.eta_min, consultas.resumo_estadia(c, e) if e else None,
        consultas.ultima_task(rota_id), consultas.ultima_ligacao(rota_id), [ev.mensagem for ev in reversed(evs)],
        pendencias(rota_id), consultas.ultimos_avisos(rota_id),
    )


def _retirada_pendente(rota_id: int) -> bool:
    from ..infra.models import EventoGeo

    r = consultas.rota(rota_id)
    with sessao() as s:
        geo = s.exec(select(EventoGeo).where(EventoGeo.rota_id == rota_id, EventoGeo.tipo == "RETIRADA")).first()
    return r.status == "na_origem" and geo is not None and geo.confirmacao_voz_em is None


def _chegada_pendente(rota_id: int) -> bool:
    from ..infra.models import EventoGeo

    r = consultas.rota(rota_id)
    with sessao() as s:
        geo = s.exec(select(EventoGeo).where(EventoGeo.rota_id == rota_id, EventoGeo.tipo == "CHEGADA")).first()
    return r.status == "no_destino" and geo is not None and geo.confirmacao_voz_em is None


def pendencias(rota_id: int) -> list[str]:
    """O que o agente ainda precisa obter do motorista (vai no estado vivo do LLM)."""
    out = []
    if _chegada_pendente(rota_id):
        out.append("Chegada detectada pelo GPS, falta a confirmação por voz: pergunte 'Confirma a chegada?' e use confirmar_chegada.")
    if _retirada_pendente(rota_id):
        out.append("Retirada na origem ainda não confirmada: pergunte 'Confirma a retirada da carga?' e use confirmar_retirada.")
    fi = reportes.faltantes_abertos(rota_id, "inicial")
    if fi:
        out.append("Relatório inicial pendente; pergunte só: " + ", ".join(reportes.ROTULOS[k] for k in fi) + " (registrar_relatorio_inicial).")
    fc = reportes.faltantes_abertos(rota_id, "checkin")
    if fc:
        out.append("Check-in pendente; pergunte só: " + ", ".join(reportes.ROTULOS[k] for k in fc) + " (registrar_checkin).")
    from ..dominio import ocorrencias as roteiro
    from . import tasks as tasks_srv

    oc = tasks_srv.ocorrencia_aberta(rota_id)
    if oc and oc.faltantes:
        out.append(f"Ocorrência de {oc.tipo} aberta: aprofunde, uma pergunta por vez. Próxima: "
                   f"'{roteiro.proxima(oc.tipo, oc.faltantes)}' (registre com detalhar_ocorrencia).")
    sol = central.pendente(rota_id)
    if sol:
        out.append(f"Pergunta da central aguardando resposta do motorista: '{sol.pergunta}' (use responder_central).")
    mensagem = mensagens.pendente(rota_id)
    if mensagem:
        out.append(
            f"Mensagem da CCO aguardando resposta, enviada por {mensagem.remetente}: "
            f"'{mensagem.texto}' (use responder_mensagem_motorista)."
        )
    return out


def _transcrever(sa: SessaoAgente, quem: str, texto: str) -> None:
    if sa.papel != Papel.RECEBEDOR or not sa.ligacao_id or not texto:
        return
    with sessao() as s:
        lig = s.get(LigacaoRecebedor, sa.ligacao_id)
        lig.transcricao = list(lig.transcricao or []) + [{"quem": quem, "texto": texto, "ts": time.time()}]
        if quem == "recebedor":
            lig.atendida = True
        s.add(lig)
        s.commit()


def estado_contingencia(c, sa: SessaoAgente) -> contingencia.Estado:
    from ..dominio.estadia import falar_horas
    from . import tasks as tasks_srv

    oc = tasks_srv.ocorrencia_aberta(sa.rota_id)
    r, nome, _ = consultas.contexto_rota(sa.rota_id)
    e = consultas.ultima_estadia(sa.rota_id)
    x = consultas.resumo_estadia(c, e) if e else None
    t = consultas.ultima_task(sa.rota_id)
    lig = consultas.ultima_ligacao(sa.rota_id)
    respondida = lig if lig and lig.status == "respondida" else None
    return contingencia.Estado(
        nome=nome.split()[0], destino=r.destino_nome, status_rota=r.status,
        tempo_parado=falar_horas(x.horas_paradas) if x else None,
        franquia_restante=falar_horas(x.franquia_restante_h) if x else None,
        valor=x.valor_fmt if x else None,
        task_status=t.status if t else None, tentativas_cco=t.tentativas if t else 0,
        doca=respondida.doca if respondida else None, previsao=respondida.previsao if respondida else None,
        resumo_recebedor=respondida.resposta_resumo if respondida else None,
        ligacao_status=lig.status if lig else None,
        retirada_pendente=_retirada_pendente(sa.rota_id),
        chegada_pendente=_chegada_pendente(sa.rota_id),
        ocorrencia_tipo=oc.tipo if oc else None,
        ocorrencia_faltantes=(list(oc.faltantes) if oc else None),
        inicial_faltantes=reportes.faltantes_abertos(sa.rota_id, "inicial"),
        checkin_faltantes=reportes.faltantes_abertos(sa.rota_id, "checkin"),
        pergunta_central=(central.pendente(sa.rota_id).pergunta if central.pendente(sa.rota_id) else None),
        ultimos_avisos=consultas.ultimos_avisos(sa.rota_id),
    )


def heuristica(c, sa: SessaoAgente, fala: str) -> tuple[Optional[str], dict, str]:
    """Contingência sem LLM: diálogo por intenção com o estado da rota (dominio/contingencia.py)."""
    d = contingencia.decidir(sa.papel, fala, estado_contingencia(c, sa))
    return d.ferramenta, d.args, d.texto


async def _executar(c, sa: SessaoAgente, nome: str, args: dict, fala: str) -> dict:
    f = ferramentas.para(sa.papel).get(nome)
    if not f:
        return {"ok": False, "erro": f"ferramenta desconhecida: {nome}"}
    log.info("ferramenta %s(%s) sessao=%s", nome, args, sa.id)
    try:
        return await f.executar(c, sa, args, fala)
    except Exception as e:  # noqa: BLE001
        log.exception("ferramenta %s falhou", nome)
        return {"ok": False, "erro": str(e)}


async def responder(c, sa: SessaoAgente, msgs_in: list[dict]) -> AsyncIterator[str]:
    """Gera o texto da resposta em pedaços (para o SSE começar antes do fim)."""
    fala = ultima_fala(msgs_in)
    if fala:
        if sa.papel == Papel.RECEBEDOR:
            c.eventos.registrar(TipoEvento.FALA_RECEBEDOR, fala, sa.rota_id, sessao_id=sa.id)
        elif sa.papel == Papel.MOTORISTA:
            c.eventos.registrar(TipoEvento.FALA_MOTORISTA, fala, sa.rota_id, sessao_id=sa.id, _fonte="driver")
            alertas.registrar(c, sa.rota_id, fala)
        else:
            c.eventos.registrar(TipoEvento.FALA_AGENTE, fala, sa.rota_id, sessao_id=sa.id, _fonte="cco")
        _transcrever(sa, "recebedor", fala)

    dito: list[str] = []

    async def contingencia():
        nome, args, texto = heuristica(c, sa, fala)
        if nome:
            res = await _executar(c, sa, nome, args, fala)
            if not texto and isinstance(res, dict):
                texto = res.get("resposta") or "Certo."
        dito.append(texto)
        return texto

    if not c.settings.llm_api_key:
        yield await contingencia()
    else:
        msgs = limpar(msgs_in)
        msgs.insert(1 if msgs and msgs[0].get("role") == "system" else 0, {"role": "system", "content": estado(c, sa.rota_id)})
        schemas = ferramentas.schemas(sa.papel)
        t0 = time.monotonic()
        for _ in range(MAX_PASSADAS):
            calls = None
            try:
                async for ev in c.llm.stream(msgs, schemas):
                    if "texto" in ev:
                        if not dito:
                            c.latencias.append((time.monotonic() - t0) * 1000)
                        dito.append(ev["texto"])
                        yield ev["texto"]
                    elif "tool_calls" in ev:
                        calls = ev["tool_calls"]
            except Exception as e:  # noqa: BLE001
                log.error("LLM upstream falhou: %s", e)
                if not dito:
                    yield await contingencia()
                break
            if not calls:
                break
            msgs.append({"role": "assistant", "content": "", "tool_calls": calls})
            for tc in calls:
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                res = await _executar(c, sa, tc["function"]["name"], args, fala)
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(res, ensure_ascii=False, default=str)})
        if not dito:
            dito.append("Certo.")
            yield "Certo."

    texto = "".join(dito).strip()
    _transcrever(sa, "agente", texto)
    c.eventos.publicar("fala", {"rota_id": sa.rota_id, "papel": sa.papel, "texto": texto}, sa.rota_id)


def sessao_da_requisicao(sid: Optional[str]) -> Optional[SessaoAgente]:
    with sessao() as s:
        if sid and str(sid).isdigit():
            return s.get(SessaoAgente, int(sid))
        return s.exec(select(SessaoAgente).where(SessaoAgente.status == "ativa").order_by(SessaoAgente.id.desc())).first()
