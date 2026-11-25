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
from tests.fakes import FakeAgora, FakeLLM, RelogioFixo

APP_ID = "0123456789abcdef0123456789abcdef"
CERT = "fedcba9876543210fedcba9876543210"


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
        agora_app_id=APP_ID,
        agora_app_certificate=CERT,
        agora_customer_id="cid",
        agora_customer_secret="csecret",
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
    )


@pytest.fixture
def fake_agora() -> FakeAgora:
    return FakeAgora()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def relogio() -> RelogioFixo:
    return RelogioFixo()


@pytest.fixture
async def container(settings, fake_agora, fake_llm, relogio):
    c = ct.Container(settings=settings, agora=fake_agora, llm=fake_llm, relogio=relogio, eventos=Eventos())
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
