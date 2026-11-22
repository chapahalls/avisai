"""Merge capacity and CCO called migration branches.

Revision ID: 9b2f0c5e1a73
Revises: 06e198860907, 7ac4e2d1f9b0
"""
from typing import Sequence, Union


revision: str = "9b2f0c5e1a73"
down_revision: Union[str, tuple[str, str], None] = ("06e198860907", "7ac4e2d1f9b0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
