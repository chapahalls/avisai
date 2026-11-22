"""API do AvisAI."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import agentes, cco, compat, ligacoes, llm, rotas
from .infra import container as ct

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("avisai")
STATIC = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = ct.atual().settings
    if not s.agora_configurada():
        log.warning("AGORA_APP_ID/AGORA_APP_CERTIFICATE ausentes")
    yield
    ct.cancelar_tarefas()


app = FastAPI(title="AvisAI API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(agentes.router)
app.include_router(ligacoes.router)
app.include_router(rotas.router)
app.include_router(llm.router)
app.include_router(cco.router)
app.include_router(compat.router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/health", tags=["infra"])
def health():
    s = ct.atual().settings
    from .integracoes.tunel import url_publica

    return {
        "ok": True,
        "agora_configurada": s.agora_configurada(),
        "auth_agora": "basic" if s.agora_customer_id else "token",
        "llm_mode": s.llm_mode,
        "llm_upstream": bool(s.llm_api_key),
        "public_url": url_publica(s),
        "recebedor_modo": s.recebedor_modo,
    }
