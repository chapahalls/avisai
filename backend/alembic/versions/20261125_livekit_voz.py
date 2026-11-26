"""Troca o identificador da sala de chamada do Agora para LiveKit."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261125_livekit"
down_revision: Union[str, None] = "d4b8e6a91c02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("chamadaagente", "agora_canal", new_column_name="livekit_room")
    op.drop_column("sessaoagente", "agent_uid")
    op.drop_column("sessaoagente", "user_uid")


def downgrade() -> None:
    op.add_column("sessaoagente", sa.Column("user_uid", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sessaoagente", sa.Column("agent_uid", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("chamadaagente", "livekit_room", new_column_name="agora_canal")
