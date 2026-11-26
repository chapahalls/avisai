"""Gateway de texto e ferramentas usado pelo worker Gemini Live do LiveKit."""
import hmac
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..servicos import conversa
from .deps import c

router = APIRouter(tags=["llm"])


def _chunk(cid: str, modelo: str, delta: dict, fim=None) -> str:
    d = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": modelo,
         "choices": [{"index": 0, "delta": delta, "finish_reason": fim}]}
    return f"data: {json.dumps(d, ensure_ascii=False)}\n\n"


@router.post("/v1/chat/completions")
@router.post("/chat/completions", include_in_schema=False)
async def chat_completions(request: Request, ct=Depends(c)):
    segredo = ct.settings.llm_shared_secret
    recebido = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if segredo and not hmac.compare_digest(recebido.encode(), segredo.encode()):
        raise HTTPException(401, "segredo inválido")
    corpo = await request.json()
    sa = conversa.sessao_da_requisicao(request.headers.get("x-avisai-sessao") or request.query_params.get("sessao"))
    if not sa:
        raise HTTPException(404, "nenhuma sessão de agente ativa")
    cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    modelo = ct.settings.llm_model
    pedacos = conversa.responder(ct, sa, corpo.get("messages", []))

    if not corpo.get("stream", True):
        texto = "".join([p async for p in pedacos]).strip()
        return JSONResponse({"id": cid, "object": "chat.completion", "created": int(time.time()), "model": modelo,
                             "choices": [{"index": 0, "message": {"role": "assistant", "content": texto}, "finish_reason": "stop"}]})

    async def gerar():
        yield _chunk(cid, modelo, {"role": "assistant", "content": ""})
        async for p in pedacos:
            yield _chunk(cid, modelo, {"content": p})
        yield _chunk(cid, modelo, {}, "stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(gerar(), media_type="text/event-stream")


def _sessao_voice(request: Request, ct):
    segredo = ct.settings.llm_shared_secret
    recebido = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if segredo and not hmac.compare_digest(recebido.encode(), segredo.encode()):
        raise HTTPException(401, "segredo inválido")
    sa = conversa.sessao_da_requisicao(request.headers.get("x-avisai-sessao"))
    if not sa or sa.status != "ativa":
        raise HTTPException(404, "nenhuma sessão de agente ativa")
    return sa


@router.post("/v1/voice/turn")
async def voice_turn(request: Request, ct=Depends(c)):
    """Persiste as transcrições do Gemini Live no mesmo fluxo de eventos do RODAR."""
    sa = _sessao_voice(request, ct)
    body = await request.json()
    papel = body.get("role")
    texto = str(body.get("text") or "")[:12000]
    if papel not in ("user", "assistant"):
        raise HTTPException(422, "role deve ser user ou assistant")
    conversa.registrar_turno(ct, sa, papel, texto)
    return {"state": conversa.estado(ct, sa.rota_id)}


@router.get("/v1/voice/context")
async def voice_context(request: Request, ct=Depends(c)):
    sa = _sessao_voice(request, ct)
    return {"state": conversa.estado(ct, sa.rota_id)}


@router.post("/v1/voice/tool")
async def voice_tool(request: Request, ct=Depends(c)):
    """Executa no backend a ferramenta chamada pelo modelo Gemini realtime."""
    sa = _sessao_voice(request, ct)
    body = await request.json()
    nome = str(body.get("name") or "")
    args = body.get("arguments") or {}
    if not isinstance(args, dict):
        raise HTTPException(422, "arguments deve ser um objeto")
    fala = str(body.get("utterance") or "")[:12000]
    return await conversa.executar_ferramenta(ct, sa, nome, args, fala)
