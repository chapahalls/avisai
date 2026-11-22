from logging.config import fileConfig

from alembic import context
from sqlmodel import SQLModel

from app.infra import models  # noqa: F401  (registra as tabelas)
from app.infra.db import engine

if context.config.config_file_name is not None and context.config.attributes.get("configure_logger", True):
    fileConfig(context.config.config_file_name, disable_existing_loggers=False)

target_metadata = SQLModel.metadata


def run_migrations_online() -> None:
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
