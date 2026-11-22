"""Merge occurrence-detail and agent-call migration branches.

Revision ID: d4b8e6a91c02
Revises: e599c7f14390, b5d75d300f31
"""
from typing import Sequence, Union


revision: str = "d4b8e6a91c02"
down_revision: Union[str, tuple[str, str], None] = ("e599c7f14390", "b5d75d300f31")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
