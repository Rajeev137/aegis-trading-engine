from fastapi import FastAPI
from app.core.config import settings
from app.api.auth import router as auth_router
from app.api.trading import router as trading_router
from app.api.market import router as market_router

app = FastAPI(
    title = settings.PROJECT_NAME,
    description = "High-throughput Execution Engine API",
    version = "1.0.0"
)

#mount the routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(trading_router, prefix="/api/v1/trading", tags=["Trading & Portfolio"])
app.include_router(market_router, prefix="/api/v1/market", tags=["Market Data"])

@app.get("/health")
async def health_check():
    """Simple health check endpoint for load balancers and docker."""
    return {"status": "Aegis execution engine is running"}
