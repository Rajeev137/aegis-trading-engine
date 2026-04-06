"""rename typre to type in transactions

Revision ID: 78d0ad16b247
Revises: 0b6ee466fb55
Create Date: 2026-04-06 21:45:47.544724

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78d0ad16b247'
down_revision: Union[str, None] = '0b6ee466fb55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "transactions",
        "typre",
        new_column_name="type",
        existing_type=sa.String(length=10),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "transactions",
        "type",
        new_column_name="typre",
        existing_type=sa.String(length=10),
        existing_nullable=False,
    )
