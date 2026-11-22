"""Chamados do motorista para o CCO e localização da ocorrência.

Revision ID: 7ac4e2d1f9b0
Revises: c921df74a130
"""
from alembic import op
import sqlalchemy as sa


revision = "7ac4e2d1f9b0"
down_revision = "c921df74a130"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ocorrencia", sa.Column("km", sa.Float(), nullable=True))
    op.add_column("ocorrencia", sa.Column("rodovia", sa.String(), nullable=True))
    op.create_table(
        "chamadocco",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rota_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("assunto", sa.String(), nullable=False),
        sa.Column("descricao", sa.String(), nullable=False),
        sa.Column("km", sa.Float(), nullable=True),
        sa.Column("rodovia", sa.String(), nullable=True),
        sa.Column("ocorrencia_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("tentativas", sa.Integer(), nullable=False),
        sa.Column("max_tentativas", sa.Integer(), nullable=False),
        sa.Column("intervalo_s", sa.Float(), nullable=False),
        sa.Column("criada_em", sa.DateTime(), nullable=False),
        sa.Column("ultima_notificacao", sa.DateTime(), nullable=True),
        sa.Column("respondida_em", sa.DateTime(), nullable=True),
        sa.Column("resposta", sa.String(), nullable=True),
        sa.Column("respondido_por", sa.String(), nullable=True),
        sa.Column("transcricao", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["ocorrencia_id"], ["ocorrencia.id"]),
        sa.ForeignKeyConstraint(["rota_id"], ["rota.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chamadocco_rota_id", "chamadocco", ["rota_id"])


def downgrade():
    op.drop_index("ix_chamadocco_rota_id", table_name="chamadocco")
    op.drop_table("chamadocco")
    op.drop_column("ocorrencia", "rodovia")
    op.drop_column("ocorrencia", "km")
