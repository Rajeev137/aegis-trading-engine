import pytest 
import pytest_asyncio
import redis.asyncio as aioredis
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.session import get_db
from app.core.cache import get_redis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from testcontainers.redis import RedisContainer
from testcontainers.postgres import PostgresContainer
from alembic.config import Config
from alembic.command import upgrade

@pytest.fixture(scope="session")
def redis_url():
    with RedisContainer("redis:7-alpine") as r:
        host = r.get_container_host_ip()
        port = r.get_exposed_port(6379)
        yield f"redis://{host}:{port}"

@pytest_asyncio.fixture(scope="session")
async def redis_client(redis_url):
    client = aioredis.from_url(redis_url)
    yield client
    await client.aclose()

@pytest.fixture(scope="session")
def postgres_url():
    with PostgresContainer("postgres:15-alpine") as pr:
        host = pr.get_container_host_ip()
        port = pr.get_exposed_port(5432)
        url = f"postgresql+asyncpg://test:test@{host}:{port}/test"
        alembic_cnf = Config("alembic.ini")
        alembic_cnf.set_main_option("sqlalchemy.url", url)
        upgrade(alembic_cnf, "head")
        yield url

@pytest_asyncio.fixture(scope="session")
async def http_client(postgres_url, redis_url, redis_client):
    # build a real async DB session pointing at the test container
    engine = create_async_engine(postgres_url)
    TestSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    
    async def override_get_db():
         async with TestSessionLocal() as session:
              yield session

    # build a real Redis client pointing at the test container
    # redis_client = aioredis.from_url(redis_url)

    async def override_get_redis():
        return redis_client
    
    # swap the app's deps
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    
     # yield an httpx client that talks to the app in-process
    async with AsyncClient(transport = ASGITransport(app=app), base_url = "http://test") as ac:
        yield ac
    
    #teardown
    app.dependency_overrides.clear()
    # await redis_client.aclose()
    await engine.dispose()

