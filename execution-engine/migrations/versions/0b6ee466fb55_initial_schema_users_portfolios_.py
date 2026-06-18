"""Initial schema: Users, Portfolios, Transactions

Revision ID: 0b6ee466fb55
Revises: 8ce016c9a318
Create Date: 2026-04-06 17:10:19.770649

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b6ee466fb55'
down_revision: Union[str, None] = '8ce016c9a318'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass  # column already created as 'type' in 8ce016c9a318


def downgrade() -> None:
    pass
