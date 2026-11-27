"""Dados do conector OCOREN: CNPJ/razão social da empresa, NF-e e embarcador da rota, campos da descarga
na estadia, e o perfil ParceiroEdi (docs/edi/ocoren-integracao.md)."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261127_edi_ocoren"
down_revision: Union[str, None] = "20261126_cancelada_geo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("empresa", sa.Column("cnpj", sa.String(), nullable=False, server_default=""))
    op.add_column("empresa", sa.Column("razao_social", sa.String(), nullable=False, server_default=""))
    op.add_column("rota", sa.Column("nfe_chave", sa.String(), nullable=False, server_default=""))
    op.add_column("rota", sa.Column("embarcador_nome", sa.String(), nullable=False, server_default=""))
    op.add_column("rota", sa.Column("embarcador_cnpj", sa.String(), nullable=False, server_default=""))
    op.add_column("rota", sa.Column("romaneio", sa.String(), nullable=False, server_default=""))
    op.add_column("estadia", sa.Column("descarga_inicio_em", sa.DateTime(), nullable=True))
    op.add_column("estadia", sa.Column("saida_destino_em", sa.DateTime(), nullable=True))
    op.create_table(
        "parceiro_edi",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("layout", sa.String(), nullable=False, server_default="ocoren-5.0"),
        sa.Column("caixa_remetente", sa.String(), nullable=False, server_default=""),
        sa.Column("caixa_destinatario", sa.String(), nullable=False, server_default=""),
        sa.Column("depara", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("campos_extras", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("codificacao", sa.String(), nullable=False, server_default="cp1252"),
        sa.Column("fim_de_linha", sa.String(), nullable=False, server_default="\r\n"),
        sa.Column("transporte", sa.String(), nullable=False, server_default="download"),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("parceiro_edi")
    op.drop_column("estadia", "saida_destino_em")
    op.drop_column("estadia", "descarga_inicio_em")
    op.drop_column("rota", "romaneio")
    op.drop_column("rota", "embarcador_cnpj")
    op.drop_column("rota", "embarcador_nome")
    op.drop_column("rota", "nfe_chave")
    op.drop_column("empresa", "razao_social")
    op.drop_column("empresa", "cnpj")
