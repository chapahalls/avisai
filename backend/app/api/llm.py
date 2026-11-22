"""Peça 3: endpoint OpenAI-compatível chamado pela nuvem da Agora (via túnel)."""
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
    if segredo and segredo not in request.headers.get("authorization", ""):
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
