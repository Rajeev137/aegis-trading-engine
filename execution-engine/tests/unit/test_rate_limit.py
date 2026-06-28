import pytest
from unittest.mock import AsyncMock
from fastapi import HTTPException
from app.core.rate_limit import check_rate_limit



@pytest.mark.asyncio
async def test_first_request_is_allowed():
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1 #first call ever
    mock_redis.ttl.return_value = 59

    await check_rate_limit("user1", "execute", mock_redis, limit=5, window=60)
    #no execption = pass

@pytest.mark.asyncio
async def test_exactly_5_request_allowed():
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 5
    mock_redis.ttl.return_value = 50

    await check_rate_limit("user1", "execute", mock_redis, limit=5, window=60)
    #no exception = pass

@pytest.mark.asyncio
async def test_over_limit_raises_429():
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 6 # one over limit of 5
    mock_redis.ttl.return_value = 45

    with pytest.raises(HTTPException) as exc:
        await check_rate_limit("user1","execute",mock_redis,limit=5,window=60)
    assert exc.value.status_code == 429

@pytest.mark.asyncio
async def test_expire_window_reset():
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1 #simulate first req
    await check_rate_limit("user1","execute",mock_redis, limit=5, window=60)
    mock_redis.expire.assert_called_once_with("rate_limit:user1:execute", 60) #assert expire() was called once with the right arguments

@pytest.mark.asyncio
async def test_subsequent_request_does_not_reset_ttl():
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 2 #simulate second req
    await check_rate_limit("user1","execute",mock_redis, limit=5, window=60)
    mock_redis.expire.assert_not_called() # assert expire not called on subsequent request and ttl not reset 

@pytest.mark.asyncio
async def test_custom_limit_and_window_respected():
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 2 # one over limit of 1
    mock_redis.ttl.return_value = 20

    with pytest.raises(HTTPException) as exc:
        await check_rate_limit("user1","execute",mock_redis,limit=1,window=30)
    assert exc.value.status_code == 429

@pytest.mark.asyncio
async def test_expire_custom_window_reset():
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1 #simulate first req
    await check_rate_limit("user1","execute",mock_redis, limit=1, window=30)
    mock_redis.expire.assert_called_once_with("rate_limit:user1:execute", 30)