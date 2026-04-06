import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default = lambda: datetime.now(timezone.utc))

class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    asset_symbol = Column(String(10), nullable=False)
    # DECIMAL(18,8) is standard for crypto to prevent floating point errors
    balance = Column(Numeric(18, 8), nullable=False, default=0)
    locked_balance = Column(Numeric(18, 8), nullable=False, default=0)

    __table_args__ = (UniqueConstraint('user_id', 'asset_symbol', name='uix_user_asset'),)

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    type = Column("type", String(10), nullable=False)  # BUY or SELL
    pair = Column(String(20), nullable=False)  # e.g. BTC/USD
    amount = Column(Numeric(18, 8), nullable=False)
    price = Column(Numeric(18, 8), nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending, completed, failed
    created_at = Column(DateTime(timezone=True), default = lambda: datetime.now(timezone.utc))



    
