"""Peça 3: conversa do LLM próprio. Estado vivo + ferramentas + streaming do texto final."""
import json
import logging
import time
from typing import AsyncIterator, Optional

from sqlmodel import select

from ..dominio import prompts
from ..dominio.enums import Papel, TipoEvento
from ..infra.db import sessao
from ..infra.models import Evento, LigacaoRecebedor, SessaoAgente
from . import consultas, ferramentas

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
    )


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


def heuristica(sa: SessaoAgente, fala: str) -> tuple[Optional[str], dict, str]:
    """Plano de contingência sem LLM: regras por palavra-chave para a demo não travar."""
    f = fala.lower()
    if sa.papel == Papel.RECEBEDOR:
        if any(p in f for p in ("doca", "minuto", "hora", "não recebe", "nao recebe", "amanhã")):
            return "registrar_resposta_recebedor", {"resumo": fala}, "Anotado. Vou passar para o motorista. Obrigada!"
        return None, {}, "Qual a previsão de descarga e a doca, por favor?"
    if any(p in f for p in ("descarreg", "terminei", "liberaram")):
        return "confirmar_descarga", {}, "Fechado, descarga registrada e estadia encerrada."
    if any(p in f for p in ("cheguei", "portaria", "no pátio")):
        return "confirmar_chegada", {}, "Chegada registrada. O contador de estadia já tá rodando."
    if any(p in f for p in ("fila", "doca", "problema")):
        return "registrar_ocorrencia", {"tipo": "fila" if "fila" in f else "outro", "descricao": fala}, "Registrei a ocorrência, o CCO vai ver."
    return None, {}, "Entendi. Tô de olho na entrega, qualquer coisa me chama."


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
        tipo = TipoEvento.FALA_RECEBEDOR if sa.papel == Papel.RECEBEDOR else TipoEvento.FALA_MOTORISTA
        c.eventos.registrar(tipo, fala, sa.rota_id, sessao_id=sa.id)
        _transcrever(sa, "recebedor", fala)

    dito: list[str] = []

    async def contingencia():
        nome, args, texto = heuristica(sa, fala)
        if nome:
            await _executar(c, sa, nome, args, fala)
        dito.append(texto)
        return texto

    if not c.settings.llm_api_key:
        yield await contingencia()
    else:
        msgs = limpar(msgs_in)
        msgs.insert(1 if msgs and msgs[0].get("role") == "system" else 0, {"role": "system", "content": estado(c, sa.rota_id)})
        schemas = ferramentas.schemas(sa.papel)
        for _ in range(MAX_PASSADAS):
            calls = None
            try:
                async for ev in c.llm.stream(msgs, schemas):
                    if "texto" in ev:
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
