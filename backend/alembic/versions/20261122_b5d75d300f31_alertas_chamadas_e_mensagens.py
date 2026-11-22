"""Alertas do motorista, chamadas do agente e threads de mensagens da CCO.

Revision ID: b5d75d300f31
Revises: 9b2f0c5e1a73
"""
from alembic import op
import sqlalchemy as sa


revision = "b5d75d300f31"
down_revision = "9b2f0c5e1a73"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mensagemmotorista",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rota_id", sa.Integer(), nullable=False),
        sa.Column("remetente", sa.String(), nullable=False),
        sa.Column("texto", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("criada_em", sa.DateTime(), nullable=False),
        sa.Column("falada_em", sa.DateTime(), nullable=True),
        sa.Column("respondida_em", sa.DateTime(), nullable=True),
        sa.Column("resposta", sa.String(), nullable=True),
        sa.Column("transcricao_resposta", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["rota_id"], ["rota.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mensagemmotorista_rota_id", "mensagemmotorista", ["rota_id"])
    op.create_table(
        "chamadaagente",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rota_id", sa.Integer(), nullable=False),
        sa.Column("destino", sa.String(), nullable=False),
        sa.Column("motivo", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("twilio_sid", sa.String(), nullable=True),
        sa.Column("twilio_resultado", sa.String(), nullable=True),
        sa.Column("agora_canal", sa.String(), nullable=True),
        sa.Column("sessao_id", sa.Integer(), nullable=True),
        sa.Column("iniciada_em", sa.DateTime(), nullable=False),
        sa.Column("atendida_em", sa.DateTime(), nullable=True),
        sa.Column("encerrada_em", sa.DateTime(), nullable=True),
        sa.Column("erro", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["rota_id"], ["rota.id"]),
        sa.ForeignKeyConstraint(["sessao_id"], ["sessaoagente.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chamadaagente_rota_id", "chamadaagente", ["rota_id"])


def downgrade():
    op.drop_index("ix_chamadaagente_rota_id", table_name="chamadaagente")
    op.drop_table("chamadaagente")
    op.drop_index("ix_mensagemmotorista_rota_id", table_name="mensagemmotorista")
    op.drop_table("mensagemmotorista")
