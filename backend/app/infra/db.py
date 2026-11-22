import os

from sqlmodel import Session, create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://avisai:avisai@db:5432/avisai")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def sessao() -> Session:
    return Session(engine, expire_on_commit=False)
