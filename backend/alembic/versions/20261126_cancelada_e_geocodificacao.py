"""Rota cancelada e endereço geocodificado de origem/destino."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261126_cancelada_geo"
down_revision: Union[str, None] = "20261125_livekit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("rota", sa.Column("cancelada_em", sa.DateTime(), nullable=True))
    op.add_column("rota", sa.Column("cancelada_por", sa.String(), nullable=True))
    op.add_column("rota", sa.Column("cancelamento_motivo", sa.String(), nullable=True))
    for lado in ("origem", "destino"):
        op.add_column("rota", sa.Column(f"{lado}_endereco", sa.String(), nullable=False, server_default=""))
        op.add_column("rota", sa.Column(f"{lado}_geo", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))


def downgrade() -> None:
    for lado in ("destino", "origem"):
        op.drop_column("rota", f"{lado}_geo")
        op.drop_column("rota", f"{lado}_endereco")
    op.drop_column("rota", "cancelamento_motivo")
    op.drop_column("rota", "cancelada_por")
    op.drop_column("rota", "cancelada_em")
