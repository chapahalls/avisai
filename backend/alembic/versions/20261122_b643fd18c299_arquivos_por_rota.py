"""Arquivos persistentes por rota.

Revision ID: b643fd18c299
Revises: 5f0f0aedef54
"""
from alembic import op
import sqlalchemy as sa

revision = "b643fd18c299"
down_revision = "5f0f0aedef54"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "arquivo_rota",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rota_id", sa.Integer(), nullable=False),
        sa.Column("nome_original", sa.String(), nullable=False),
        sa.Column("tipo_mime", sa.String(), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer(), nullable=False),
        sa.Column("categoria", sa.String(), nullable=False),
        sa.Column("descricao", sa.String(), nullable=True),
        sa.Column("chave_storage", sa.String(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["rota_id"], ["rota.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chave_storage"),
    )
    op.create_index("ix_arquivo_rota_rota_id", "arquivo_rota", ["rota_id"])


def downgrade():
    op.drop_index("ix_arquivo_rota_rota_id", table_name="arquivo_rota")
    op.drop_table("arquivo_rota")
