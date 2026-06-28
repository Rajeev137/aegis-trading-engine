import pytest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.api.trading import execute_trade
from app.api.schemas import TradeExecuteRequest
from app.db.models import User, Transaction, Portfolio


def fake_user():
    mock_user = User()
    mock_user.id = uuid.uuid4()
    mock_user.email = "test@example.com"
    return mock_user

async def fake_db(usd_wallet, btc_wallet):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [usd_wallet, btc_wallet]
    async def fake_refresh(obj):
          if isinstance(obj, Transaction):
                obj.id = uuid.uuid4()
                obj.created_at = datetime.now(timezone.utc)
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.return_value = mock_result
    db.refresh.side_effect = fake_refresh
    return db

def fake_redis():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = Decimal("50000")
    mock_redis.incr.return_value = 1
    mock_redis.ttl.return_value = -1
    return mock_redis

@pytest.mark.asyncio
async def test_buy_with_sufficient_usd():
    user = fake_user()
    usd_wallet = Portfolio()
    usd_wallet.user_id = user.id
    usd_wallet.asset_symbol = "USD"
    usd_wallet.balance = Decimal("20000")

    btc_wallet = Portfolio()
    btc_wallet.user_id = user.id
    btc_wallet.asset_symbol = "BTC"
    btc_wallet.balance = Decimal("0")

    db = await fake_db(usd_wallet, btc_wallet)
    redis = fake_redis()
    trade = TradeExecuteRequest(type= "BUY", pair= "BTC-USD", amount= Decimal("0.1"))

    result = await execute_trade(
         trade_in= trade,
         current_user=user,
         db=db,
         redis_client=redis
    )

    assert usd_wallet.balance == Decimal("15000")
    assert btc_wallet.balance == Decimal("0.1")

    assert result.type == "BUY"
    assert result.pair == "BTC-USD"
    assert result.amount == Decimal("0.1")
    assert result.price == Decimal("50000")
    assert result.status == "COMPLETED"
    assert result.user_id == user.id

    db.commit.assert_awaited_once()
     