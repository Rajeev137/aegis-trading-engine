import pytest
import uuid
from fastapi import HTTPException
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
    mock_redis.get.return_value = b"50000"
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
    
@pytest.mark.asyncio
async def test_buy_with_unsufficient_usd():
    user = fake_user()
    usd_wallet = Portfolio()
    usd_wallet.user_id = user.id
    usd_wallet.asset_symbol = "USD"
    usd_wallet.balance = Decimal("1")

    btc_wallet = Portfolio()
    btc_wallet.user_id = user.id
    btc_wallet.asset_symbol = "BTC"
    btc_wallet.balance = Decimal("0")
    db = await fake_db(usd_wallet, btc_wallet)
    redis = fake_redis()
    trade = TradeExecuteRequest(type= "BUY", pair= "BTC-USD", amount= Decimal("0.1"))

    with pytest.raises(HTTPException) as exc:
        await execute_trade(
            trade_in= trade,
            current_user=user,
            db=db,
            redis_client=redis)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Insufficient funds"
    db.rollback.assert_awaited_once()
         
         
@pytest.mark.asyncio
async def test_sell_with_sufficient_btc():
    user = fake_user()
    usd_wallet = Portfolio()
    usd_wallet.user_id = user.id
    usd_wallet.asset_symbol = "USD"
    usd_wallet.balance = Decimal("0")

    btc_wallet = Portfolio()
    btc_wallet.user_id = user.id
    btc_wallet.asset_symbol = "BTC"
    btc_wallet.balance = Decimal("0.1")

    db = await fake_db(usd_wallet, btc_wallet)
    redis = fake_redis()
    trade = TradeExecuteRequest(type= "SELL", pair= "BTC-USD", amount= Decimal("0.1"))

    result = await execute_trade(
         trade_in= trade,
         current_user=user,
         db=db,
         redis_client=redis
    )

    assert usd_wallet.balance == Decimal("5000")
    assert btc_wallet.balance == Decimal("0")

    assert result.type == "SELL"
    assert result.pair == "BTC-USD"
    assert result.amount == Decimal("0.1")
    assert result.price == Decimal("50000")
    assert result.status == "COMPLETED"
    assert result.user_id == user.id

    db.commit.assert_awaited_once()

@pytest.mark.asyncio
async def test_sell_with_unsufficient_btc():
    user = fake_user()
    usd_wallet = Portfolio()
    usd_wallet.user_id = user.id
    usd_wallet.asset_symbol = "USD"
    usd_wallet.balance = Decimal("0")

    btc_wallet = Portfolio()
    btc_wallet.user_id = user.id
    btc_wallet.asset_symbol = "BTC"
    btc_wallet.balance = Decimal("0")
    db = await fake_db(usd_wallet, btc_wallet)
    redis = fake_redis()
    trade = TradeExecuteRequest(type= "SELL", pair= "BTC-USD", amount= Decimal("0.1"))

    with pytest.raises(HTTPException) as exc:
        await execute_trade(
            trade_in= trade,
            current_user=user,
            db=db,
            redis_client=redis)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Insufficient asset balance"
    db.rollback.assert_awaited_once()

@pytest.mark.asyncio
async def test_invalid_trade_type():
    user = fake_user()
    usd_wallet = Portfolio()
    usd_wallet.user_id = user.id
    usd_wallet.asset_symbol = "USD"
    usd_wallet.balance = Decimal("20000")

    btc_wallet = Portfolio()
    btc_wallet.user_id = user.id
    btc_wallet.asset_symbol = "BTC"
    btc_wallet.balance = Decimal("1")
    db = await fake_db(usd_wallet, btc_wallet)
    redis = fake_redis()
    trade = TradeExecuteRequest(type= "HOLD", pair= "BTC-USD", amount= Decimal("0.1"))

    with pytest.raises(HTTPException) as exc:
        await execute_trade(
            trade_in= trade,
            current_user=user,
            db=db,
            redis_client=redis)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid trade type. Must be BUY or SELL."

@pytest.mark.asyncio
async def test_invalid_pair_format():
    user = fake_user()
    usd_wallet = Portfolio()
    usd_wallet.user_id = user.id
    usd_wallet.asset_symbol = "USD"
    usd_wallet.balance = Decimal("20000")

    btc_wallet = Portfolio()
    btc_wallet.user_id = user.id
    btc_wallet.asset_symbol = "BTC"
    btc_wallet.balance = Decimal("1")
    db = await fake_db(usd_wallet, btc_wallet)
    redis = fake_redis()
    trade = TradeExecuteRequest(type= "BUY", pair= "BTCUSD", amount= Decimal("0.1"))

    with pytest.raises(HTTPException) as exc:
        await execute_trade(
            trade_in= trade,
            current_user=user,
            db=db,
            redis_client=redis)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid pair format. Use BASE-QUOTE, e.g. BTC-USD."

@pytest.mark.asyncio
async def test_no_live_price_in_Redis():
    user = fake_user()
    usd_wallet = Portfolio()
    usd_wallet.user_id = user.id
    usd_wallet.asset_symbol = "USD"
    usd_wallet.balance = Decimal("20000")

    btc_wallet = Portfolio()
    btc_wallet.user_id = user.id
    btc_wallet.asset_symbol = "BTC"
    btc_wallet.balance = Decimal("1")
    db = await fake_db(usd_wallet, btc_wallet)
    redis = fake_redis()
    redis.get.return_value = None
    trade = TradeExecuteRequest(type= "BUY", pair= "BTC-USD", amount= Decimal("0.1"))
    with pytest.raises(HTTPException) as exc:
        await execute_trade(
            trade_in= trade,
            current_user=user,
            db=db,
            redis_client=redis)
    assert exc.value.status_code == 503
    assert exc.value.detail == (f"No live price available for {trade.pair}. "
                                "Ensure the ingestion gateway is subscribed to this pair (check PAIRS env var).")
@pytest.mark.asyncio
async def test_price_always_from_redis_not_client():
    user = fake_user()
    usd_wallet = Portfolio()
    usd_wallet.user_id = user.id
    usd_wallet.asset_symbol = "USD"
    usd_wallet.balance = Decimal("20000")

    btc_wallet = Portfolio()
    btc_wallet.user_id = user.id
    btc_wallet.asset_symbol = "BTC"
    btc_wallet.balance = Decimal("1")
    db = await fake_db(usd_wallet, btc_wallet)
    redis = fake_redis()
    trade = TradeExecuteRequest(type= "BUY", pair= "BTC-USD", amount= Decimal("0.1"))

    await execute_trade(
      trade_in= trade,
      current_user=user,
      db=db,
      redis_client=redis)
    redis.get.assert_awaited_once_with("orderbook:BTC-USD:price")