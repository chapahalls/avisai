"""Falas gravadas sem sinal (offline-first).

Sem rede o app não roda modelo nenhum: grava cada fala do motorista como áudio e põe na
fila (outbox). Quando a rede volta, cada áudio chega aqui com a chave de idempotência e o
horário em que foi falado. O backend guarda o arquivo, transcreve e passa o texto ao mesmo
agente da conversa online, que registra o que a fala pede. A resposta vira aviso ao motorista.
Uma fala por vez em cada rota, na ordem de chegada (que é a ordem em que foram faladas).
O áudio é apagado depois de transcrito com sucesso: só a transcrição fica registrada no
evento. Se a transcrição falhar, o arquivo permanece em disco para permitir diagnóstico.
"""
import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from ..dominio import prompts
from ..dominio.enums import Papel, TipoEvento
from ..infra.db import sessao
from ..infra.eventos import envelope
from ..infra.models import Evento, SessaoAgente
from . import consultas, conversa
from .sessoes import VozLiveKit

log = logging.getLogger("avisai.falas_offline")

EXTENSAO = {"audio/wav": ".wav", "audio/mp4": ".m4a"}
_travas: dict[int, asyncio.Lock] = {}


def formato(cabecalho: bytes) -> Optional[str]:
    if cabecalho[:4] == b"RIFF" and cabecalho[8:12] == b"WAVE":
        return "audio/wav"
    if cabecalho[4:8] == b"ftyp":
        return "audio/mp4"
    return None


def quando(texto: Optional[str], padrao: datetime) -> datetime:
    """ISO do app → UTC com tzinfo (mesmo formato do relógio). Inválido ou no futuro: usa `padrao`."""
    try:
        dt = datetime.fromisoformat((texto or "").replace("Z", "+00:00"))
    except ValueError:
        return padrao
    dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    if padrao.tzinfo is None:
        padrao = padrao.replace(tzinfo=UTC)
    return min(dt, padrao)


def hora_local(c, dt: datetime) -> str:
    return (dt + timedelta(hours=c.settings.fuso_utc_horas)).strftime("%Hh%M")


def _pasta(c) -> Path:
    pasta = Path(c.settings.falas_offline_dir)
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _por_chave(chave: str) -> Optional[Evento]:
    with sessao() as s:
        return s.exec(select(Evento).where(Evento.idempotency_key == chave)).first()


async def receber(c, rota_id: int, chave: str, falado_em: Optional[str], duracao_ms: Optional[int],
                  arquivo: UploadFile) -> tuple[Evento, bool]:
    """Guarda o áudio e registra o evento. Devolve (evento, novo); repetido não grava de novo."""
    consultas.rota(rota_id)
    chave = (chave or "").strip()
    if not chave or len(chave) > 200:
        raise HTTPException(422, "idempotencyKey obrigatória")
    existente = _por_chave(chave)
    if existente:
        return existente, False

    limite = c.settings.falas_offline_max_bytes
    audio = await arquivo.read(limite + 1)
    if len(audio) > limite:
        raise HTTPException(413, "Áudio excede o limite permitido")
    tipo_mime = formato(audio[:16])
    if not tipo_mime:
        raise HTTPException(415, "Formato de áudio não suportado (WAV ou M4A)")

    agora = c.relogio.agora()
    dito_em = quando(falado_em, agora)
    nome = uuid.uuid4().hex + EXTENSAO[tipo_mime]
    caminho = _pasta(c) / nome
    caminho.write_bytes(audio)
    try:
        with sessao() as s:
            ev = Evento(
                rota_id=rota_id, idempotency_key=chave, source="driver", tipo=str(TipoEvento.FALA_OFFLINE),
                mensagem=f"Mensagem de voz gravada sem sinal às {hora_local(c, dito_em)}",
                dados={"arquivo": nome, "tipo_mime": tipo_mime, "tamanho_bytes": len(audio),
                       "duracao_ms": duracao_ms, "falado_em": dito_em.isoformat(), "status": "recebida"},
            )
            s.add(ev)
            s.commit()
            s.refresh(ev)
    except IntegrityError:
        # Duas entregas simultâneas da mesma fala: fica a primeira.
        caminho.unlink(missing_ok=True)
        return _por_chave(chave), False
    c.eventos.publicar("evento", envelope(ev), rota_id)
    return ev, True


def _atualizar(evento_id: int, **campos) -> Evento:
    with sessao() as s:
        ev = s.get(Evento, evento_id)
        ev.dados = {**(ev.dados or {}), **campos}
        s.add(ev)
        s.commit()
        s.refresh(ev)
    return ev


async def processar(c, evento_id: int) -> None:
    with sessao() as s:
        ev = s.get(Evento, evento_id)
    if not ev:
        return
    trava = _travas.setdefault(ev.rota_id, asyncio.Lock())
    async with trava:
        await _processar(c, ev)


async def _processar(c, ev: Evento) -> None:
    dados = ev.dados or {}
    dito_em = quando(dados.get("falado_em"), c.relogio.agora())
    hora = hora_local(c, dito_em)
    if not c.transcritor:
        _atualizar(ev.id, status="sem_transcricao")
        return
    caminho = Path(c.settings.falas_offline_dir) / dados["arquivo"]
    try:
        audio = caminho.read_bytes()
        texto = await c.transcritor.transcrever(audio, dados["arquivo"], dados["tipo_mime"])
    except Exception as e:  # noqa: BLE001
        log.warning("transcrição da fala offline %s falhou: %s", ev.id, e)
        _atualizar(ev.id, status="erro_transcricao", erro=str(e)[:300])
        return
    caminho.unlink(missing_ok=True)  # transcrito: apaga o áudio, só a transcrição fica registrada
    if not texto:
        _atualizar(ev.id, status="vazia")
        return
    _atualizar(ev.id, status="transcrita", transcricao=texto)

    r, nome, empresa = consultas.contexto_rota(ev.rota_id)
    sistema, _ = prompts.motorista(r, nome, empresa)
    atraso_min = max(0, int((c.relogio.agora() - dito_em).total_seconds() // 60))
    msgs = [
        {"role": "system", "content": sistema},
        {"role": "system", "content": prompts.fala_offline(hora, atraso_min)},
        {"role": "user", "content": texto},
    ]
    with sessao() as s:
        sa = SessaoAgente(rota_id=ev.rota_id, papel=Papel.MOTORISTA, canal=f"offline-{ev.rota_id}",
                          status="encerrada", llm_mode="custom", criada_em=c.relogio.agora(),
                          erro="fala gravada sem sinal")
        s.add(sa)
        s.commit()
        s.refresh(sa)
    resposta = "".join([parte async for parte in conversa.responder(c, sa, msgs)]).strip()
    _atualizar(ev.id, status="processada", resposta=resposta, sessao_id=sa.id)
    if resposta:
        await VozLiveKit(c).falar_motorista(ev.rota_id, f"Sobre o que você falou às {hora}: {resposta}")
