"""Persiste o nº de sequência do OCOREN em Empresa (era um dict em memória em servicos/edi.py, que
colidia entre instâncias/reinícios)."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261127_seq_ocoren"
down_revision: Union[str, None] = "20261127_edi_ocoren"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("empresa", sa.Column("ultima_sequencia_ocoren", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("empresa", "ultima_sequencia_ocoren")
