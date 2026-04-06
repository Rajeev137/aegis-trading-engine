from fastapi import APIRouter, Depends, HTTPException
import redis.asyncio as redis
from app.core.cache import get_redis

router = APIRouter()

@router.get("/price/{pair}")
async def get_live_price(pair: str, redis_client: redis.Redis = Depends(get_redis)):
    """Fetch the ultra-fast live price from Redis."""
    price = await redis_client.get(f"orderbook:{pair}:price")
    if not price:
        # Fallback dummy price if Redis is empty
        return {"pair": pair, "price": 65000.00, "source": "fallback"}
    return {"pair": pair, "price": float(price), "source": "redis"}

@router.post("/admin/set-price")
async def set_market_price(pair: str, price: float, redis_client: redis.Redis = Depends(get_redis)):
    """DEV ONLY: Simulate the WebSocket ingestion gateway updating the price."""
    await redis_client.set(f"orderbook:{pair}:price", price)
    return {"message": f"Live price of {pair} updated to {price} in Redis"}