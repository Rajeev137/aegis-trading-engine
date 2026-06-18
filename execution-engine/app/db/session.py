import os 
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

load_dotenv()

Database_URL = os.getenv("DATABASE_URL")

# Create an asynchronous engine
engine = create_async_engine(Database_URL, echo=False, future=True)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db():
    """ Dependency function for fastAPI to injest async sessions """
    async with async_session() as session:
        yield session
