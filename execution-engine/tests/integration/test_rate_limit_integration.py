import pytest
from fastapi import HTTPException
from app.core.rate_limit import check_rate_limit
import redis.asyncio as aioredis

        
@pytest.mark.asyncio
async def test_5_calls_within_limit(redis_url):
    client = aioredis.from_url(redis_url)
    for i in range(5):
        await check_rate_limit("test-user", "execute", client, limit=5, window=60)
    await client.aclose()

@pytest.mark.asyncio
async def test_counter_reset_after_window_expire(redis_url):
    client = aioredis.from_url(redis_url)
    for i in range(5):
        await check_rate_limit("reset-user", "execute", client, limit=5, window=60)
    await client.delete("rate_limit:reset-user:execute")
    await check_rate_limit("reset-user", "execute", client, limit=5, window=60)
    await client.aclose()

@pytest.mark.asyncio
async def test_fail_at_6th_call(redis_url):
    client = aioredis.from_url(redis_url)
    for i in range(5):
        await check_rate_limit("sixth-user","execute", client, limit=5, window=60)
    with pytest.raises(HTTPException) as exc:
      await check_rate_limit("sixth-user", "execute", client, limit=5, window=60)
    assert exc.value.status_code == 429 
    await client.aclose()

@pytest.mark.asyncio
async def test_key_format_exists_in_Redis(redis_url):
    client = aioredis.from_url(redis_url)
    await check_rate_limit("some-user","execute", client, limit=5, window=60)
    assert await client.exists("rate_limit:some-user:execute") == 1
    await client.aclose()

    

