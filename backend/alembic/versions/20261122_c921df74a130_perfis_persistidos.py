"""Perfis persistidos de CCO e motoristas.

Revision ID: c921df74a130
Revises: b643fd18c299
"""
from alembic import op
import sqlalchemy as sa

revision = "c921df74a130"
down_revision = "b643fd18c299"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usuario",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("nome", sa.String(), nullable=True),
        sa.Column("papel", sa.String(), nullable=False),
        sa.Column("motorista_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["motorista_id"], ["motorista.id"]),
        sa.UniqueConstraint("motorista_id"),
        sa.CheckConstraint(
            "(papel = 'cco' AND motorista_id IS NULL AND nome IS NOT NULL) OR "
            "(papel = 'driver' AND motorista_id IS NOT NULL AND nome IS NULL)",
            name="ck_usuario_papel_identidade",
        ),
    )
    op.create_index("ix_usuario_email", "usuario", ["email"], unique=True)
    # Preserva todos os motoristas. E-mails legados ambíguos não selecionam uma
    # pessoa arbitrária: só identidades únicas recebem perfil automaticamente.
    op.execute("""
        INSERT INTO usuario (email, nome, papel, motorista_id)
        SELECT known.email, NULL, 'driver', known.id
        FROM (
            SELECT lower(trim(email)) AS email, min(id) AS id
            FROM motorista
            WHERE email IS NOT NULL
              AND length(trim(email)) <= 320
              AND trim(email) ~ '^[^[:space:]@]+@[^[:space:]@]+$'
            GROUP BY lower(trim(email))
            HAVING count(*) = 1
        ) AS known
    """)


def downgrade():
    op.drop_index("ix_usuario_email", table_name="usuario")
    op.drop_table("usuario")
