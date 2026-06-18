from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from decimal import Decimal

from app.db.session import get_db
from app.db.models import User, Portfolio, Transaction
from app.api import schemas
from app.api.deps import get_current_user
from app.core.cache import get_redis, redis_client as redis_type
from app.core.rate_limit import check_rate_limit

router = APIRouter()

@router.get("/portfolio", response_model=List[schemas.PortfolioResponse])
async def get_portfolio(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(Portfolio).where(Portfolio.user_id == current_user.id)
    result = await db.execute(query)
    portfolio_items = result.scalars().all()
    return portfolio_items

@router.post("/faucet")
async def fund_test_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: redis_type = Depends(get_redis) # Inject Redis
):
    # Enforce Rate Limit: 1 request per 60 seconds
    await check_rate_limit(str(current_user.id), "faucet", redis_client, limit=1, window=60)

    """Dev ONLY endpoint to fund test accounts with fake $100000 assets for testing."""
    query = select(Portfolio).where(Portfolio.user_id == current_user.id, Portfolio.asset_symbol == "USD")
    result = await db.execute(query)
    portfolio = result.scalars().first()

    if portfolio:
        portfolio.balance += 100000
    else:
        portfolio = Portfolio(user_id=current_user.id, asset_symbol="USD", balance=100000)
        db.add(portfolio)
    await db.commit()
    return {"message": "Test account funded with $100000 USD"}

@router.post("/execute", response_model=schemas.TransactionResponse)
async def execute_trade(
    trade_in: schemas.TradeExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: redis_type = Depends(get_redis) # Inject Redis
):
    # Enforce Rate Limit: 5 requests per 60 seconds
    await check_rate_limit(str(current_user.id), "execute", redis_client, limit=5, window=60)

    # Basic validation
    if trade_in.type not in ['BUY', 'SELL']:
        raise HTTPException(status_code=400, detail="Invalid trade type. Must be BUY or SELL.")
        
    base_asset, quote_asset = trade_in.pair.split('-') # e.g., 'BTC' and 'USD'
    # --- NEW SECURITY LAYER: Fetch price from Redis ---
    live_price_str = await redis_client.get(f"orderbook:{trade_in.pair}:price")
    if not live_price_str:
        # Fallback for testing if you haven't set the price yet
        live_price = Decimal('65000.00')
    else:
        live_price = Decimal(live_price_str)

    total_cost = trade_in.amount * live_price # Use the server's price!

    try:
        # 1. Fetch relevant portfolio balances (USD and BTC)
        portfolios_query = select(Portfolio).where(Portfolio.user_id == current_user.id)
        result = await db.execute(portfolios_query)
        portfolios = {p.asset_symbol: p for p in result.scalars().all()}

        quote_wallet = portfolios.get(quote_asset)
        base_wallet = portfolios.get(base_asset)

        # Ensure wallets exist
        if not quote_wallet:
            quote_wallet = Portfolio(user_id=current_user.id, asset_symbol=quote_asset, balance=0)
            db.add(quote_wallet)
        if not base_wallet:
            base_wallet = Portfolio(user_id=current_user.id, asset_symbol=base_asset, balance=0)
            db.add(base_wallet)

        # 2. Execute Business Logic & Update Balances
        if trade_in.type == 'BUY':
            if quote_wallet.balance < total_cost:
                raise ValueError("Insufficient funds")
            quote_wallet.balance -= total_cost
            base_wallet.balance += trade_in.amount
            
        elif trade_in.type == 'SELL':
            if base_wallet.balance < trade_in.amount:
                raise ValueError("Insufficient asset balance")
            base_wallet.balance -= trade_in.amount
            quote_wallet.balance += total_cost

        # 3. Create Transaction Ledger Record
        transaction = Transaction(
            user_id=current_user.id,
            type=trade_in.type,
            pair=trade_in.pair,
            amount=trade_in.amount,
            price=live_price, # Record the price used for this trade
            status='COMPLETED'
        )
        db.add(transaction)

        # 4. Atomic Commit
        await db.commit()
        await db.refresh(transaction)
        return transaction

    except ValueError as e:
        await db.rollback() # Abort the transaction
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback() # Catch-all safety net
        raise HTTPException(status_code=500, detail="Internal Server Error during trade execution")
