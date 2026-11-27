import os

from sqlalchemy import text
from sqlmodel import Session, create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://avisai:avisai@db:5432/avisai")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def sessao() -> Session:
    return Session(engine, expire_on_commit=False)


def banco_ok() -> bool:
    """Testa a conexão de verdade; `/health` usa isso para não dizer "ok" com o banco fora."""
    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
