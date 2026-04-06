from fastapi import HTTPException, status
import redis.asyncio as redis

async def check_rate_limit(user_id: str, endpoint: str, redis_client: redis.Redis, limit: int = 5, window: int = 60):
    """
    Checks if a user has exceeded their API rate limit for a specific endpoint.
    """
    # Create a unique key for this user and endpoint, e.g., "rate_limit:user-123:/execute"
    key = f"rate_limit:{user_id}:{endpoint}"
    
    # Increment the counter for this key
    current_count = await redis_client.incr(key)
    
    # If this is the first request in the window, set the expiration timer
    if current_count == 1:
        await redis_client.expire(key, window)
        
    if current_count > limit:
        # Get remaining time before the limit resets
        ttl = await redis_client.ttl(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {ttl} seconds."
        )