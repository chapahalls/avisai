"""API do RODAR."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import agentes, arquivos, cco, compat, ligacoes, llm, rotas, usuarios
from .infra.upload_limit import UploadLimitMiddleware
from .infra import container as ct
from .infra.settings import Settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("avisai")
STATIC = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = ct.atual().settings
    if not s.agora_configurada():
        log.warning("AGORA_APP_ID/AGORA_APP_CERTIFICATE ausentes")
    if s.llm_mode == "custom" and not s.llm_shared_secret:
        log.warning("LLM_SHARED_SECRET vazio: qualquer um com a URL pública pode chamar /v1/chat/completions")
    yield
    ct.cancelar_tarefas()


app = FastAPI(title="RODAR API", version="0.1.0", lifespan=lifespan)
_cors = Settings().cors_origens  # lido no import: o middleware é montado antes do lifespan
app.add_middleware(CORSMiddleware, allow_origins=_cors, allow_methods=["*"], allow_headers=["*"],
                   allow_credentials="*" not in _cors)
app.add_middleware(UploadLimitMiddleware)
app.include_router(arquivos.router)
app.include_router(usuarios.router)
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
        "twilio_configurado": s.twilio_configurada(),
        "auth_agora": "basic" if s.agora_customer_id else "token",
        "llm_mode": s.llm_mode,
        "llm_upstream": bool(s.llm_api_key),
        "public_url": url_publica(s),
        "recebedor_modo": s.recebedor_modo,
        "auth_obrigatoria": s.auth_obrigatoria,
        "llm_protegido": bool(s.llm_shared_secret),
    }
