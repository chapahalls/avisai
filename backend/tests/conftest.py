import asyncio

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.infra import container as ct
from app.infra.db import engine
from app.infra.eventos import Eventos
from app.infra.settings import Settings
from app.seed import seed
from tests.fakes import FakeLiveKit, FakeLLM, FakeTranscritor, RelogioFixo


@pytest.fixture(scope="session", autouse=True)
def _migracoes():
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _limpar_banco():
    with engine.begin() as c:
        tabelas = [r[0] for r in c.execute(text(
            "select tablename from pg_tables where schemaname='public' and tablename <> 'alembic_version'"
        ))]
        if tabelas:
            c.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tabelas) + " RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture(autouse=True)
def _limpar_limites():
    from app.infra.auth import limite_chamadas

    limite_chamadas.limpar()
    yield


@pytest.fixture
def settings() -> Settings:
    return Settings(
        livekit_url="wss://livekit.test",
        livekit_api_key="test-key",
        livekit_api_secret="test-secret",
        public_url="https://avisai.test",
        llm_api_key="sk-test",
        llm_shared_secret="segredo",
        llm_mode="custom",
        recebedor_modo="rtc",
        cco_intervalo_s=0.01,
        ligacao_timeout_s=0.3,
        ligacao_poll_s=0.05,
        encerrar_ligacao_apos_s=0.01,
        estadia_aceleracao=1,
        # Os testes de fluxo exercitam regras de negócio; tests/api/test_auth.py liga o login e testa o acesso.
        auth_obrigatoria=False,
    )


@pytest.fixture
def fake_livekit() -> FakeLiveKit:
    return FakeLiveKit()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def fake_transcritor() -> FakeTranscritor:
    return FakeTranscritor()


@pytest.fixture
def relogio() -> RelogioFixo:
    return RelogioFixo()


@pytest.fixture
async def container(settings, fake_livekit, fake_llm, fake_transcritor, relogio, tmp_path):
    settings.falas_offline_dir = str(tmp_path / "falas_offline")
    c = ct.Container(settings=settings, livekit=fake_livekit, llm=fake_llm, transcritor=fake_transcritor,
                     relogio=relogio, eventos=Eventos())
    ct.definir(c)
    yield c
    pendentes = [t for t in c.tarefas.values() if not t.done()]
    for t in pendentes:
        t.cancel()
    await asyncio.gather(*pendentes, return_exceptions=True)


@pytest.fixture
async def rota_id(container) -> int:
    return seed()


@pytest.fixture
async def client(container, rota_id):
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
