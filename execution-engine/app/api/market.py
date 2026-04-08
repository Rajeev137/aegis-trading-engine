from fastapi import APIRouter, Depends, HTTPException
import redis.asyncio as redis
from app.core.cache import get_redis

router = APIRouter()


@router.get("/price/{pair}")
async def get_live_price(pair: str, redis_client: redis.Redis = Depends(get_redis)):
    """Fetch the ultra-fast live price from Redis."""
    price = await redis_client.get(f"orderbook:{pair}:price")
    if not price:
        raise HTTPException(
            status_code=503, detail=f"Live price for {pair} is not available. Ingestion gateway may be down.")
    return {"pair": pair, "price": float(price), "source": "live"}
