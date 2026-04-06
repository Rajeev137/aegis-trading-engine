import os
import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create a global Redis connection pool
redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)

async def get_redis():
    """Dependency to inject the Redis client."""
    yield redis_client