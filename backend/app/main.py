"""API do RODAR."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from .api import agentes, arquivos, cco, compat, falas_offline, ligacoes, livekit, llm, rotas, usuarios
from .infra.upload_limit import UploadLimitMiddleware
from .infra import container as ct
from .infra.settings import Settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("avisai")
STATIC = Path(__file__).resolve().parent.parent / "static"


AUTH_SEGREDO_MIN = 32


def checar_segredo_auth(s: Settings) -> None:
    """Com login obrigatório, o segredo do JWT precisa ser fixo: um segredo temporário derruba os tokens a cada reinício."""
    if s.auth_obrigatoria and len(s.auth_segredo) < AUTH_SEGREDO_MIN:
        raise RuntimeError(
            f"AUTH_OBRIGATORIA=true exige AUTH_SEGREDO com pelo menos {AUTH_SEGREDO_MIN} caracteres. "
            'Gere com: python -c "import secrets; print(secrets.token_urlsafe(48))". '
            "Só em desenvolvimento local: AUTH_OBRIGATORIA=false."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = ct.atual().settings
    checar_segredo_auth(s)
    if not s.auth_obrigatoria:
        log.warning("AUTH_OBRIGATORIA=false: escrita sem login liberada (só para desenvolvimento)")
    if not s.livekit_configurada():
        log.warning("LIVEKIT_URL/LIVEKIT_API_KEY/LIVEKIT_API_SECRET ausentes")
    if not s.llm_shared_secret:
        log.warning("LLM_SHARED_SECRET vazio: qualquer um com a URL pública pode chamar /v1/chat/completions")
    yield
    ct.cancelar_tarefas()


app = FastAPI(title="RODAR API", version="0.1.0", lifespan=lifespan)
_cors = Settings().cors_origens  # lido no import: o middleware é montado antes do lifespan
app.add_middleware(CORSMiddleware, allow_origins=_cors, allow_methods=["*"], allow_headers=["*"],
                   allow_credentials="*" not in _cors)
app.add_middleware(UploadLimitMiddleware)
app.include_router(arquivos.router)
app.include_router(falas_offline.router)
app.include_router(usuarios.router)
app.include_router(agentes.router)
app.include_router(ligacoes.router)
app.include_router(rotas.router)
app.include_router(llm.router)
app.include_router(cco.router)
app.include_router(compat.router)
app.include_router(livekit.router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/health", tags=["infra"])
def health():
    s = ct.atual().settings
    from .integracoes.tunel import url_publica

    return {
        "ok": True,
        "livekit_configurada": s.livekit_configurada(),
        "twilio_configurado": s.twilio_configurada(),
        "llm_mode": "custom",
        "llm_upstream": bool(s.llm_api_key),
        "public_url": url_publica(s),
        "recebedor_modo": s.recebedor_modo,
        "auth_obrigatoria": s.auth_obrigatoria,
        "llm_protegido": bool(s.llm_shared_secret),
    }

if __name__ == "__main__":
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
