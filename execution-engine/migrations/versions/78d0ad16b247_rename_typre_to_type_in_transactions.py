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
    pass  # column already named 'type' from initial schema


def downgrade() -> None:
    pass
