"""
FinSight API - Main Application
Production-ready financial data API with monetization
"""

import os
import structlog
import asyncpg
import redis.asyncio as redis
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from src.auth.api_keys import APIKeyManager
from src.billing.stripe_integration import StripeManager
from src.middleware.auth import AuthMiddleware
from src.middleware.rate_limiter import RateLimitMiddleware
from src.data_sources.sec_edgar import SECEdgarSource
from src.data_sources import register_source

# Initialize Sentry for error tracking (production)
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    import sentry_sdk
    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.getenv("ENVIRONMENT", "production"),
        traces_sample_rate=0.1,  # 10% of transactions for performance monitoring
        profiles_sample_rate=0.1,  # 10% profiling
    )

logger = structlog.get_logger(__name__)

# Global instances
db_pool: asyncpg.Pool = None
redis_client: redis.Redis = None
api_key_manager: APIKeyManager = None
stripe_manager: StripeManager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global db_pool, redis_client, api_key_manager, stripe_manager

    # Startup
    logger.info("Starting FinSight API", version="1.0.0")

    # Connect to database
    database_url = os.getenv("DATABASE_URL", "postgresql://localhost/finsight_production")
    try:
        db_pool = await asyncpg.create_pool(
            database_url,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        logger.info("Database pool created")
    except Exception as e:
        logger.warning("Database connection failed - running in degraded mode", error=str(e))
        db_pool = None

    # Connect to Redis
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        redis_client = await redis.from_url(
            redis_url,
            decode_responses=True,
            ssl_cert_reqs="none"  # Required for Heroku Redis TLS
        )
        logger.info("Redis connected")
    except Exception as e:
        logger.warning("Redis connection failed - caching/rate limiting disabled", error=str(e))
        redis_client = None

    # Initialize managers
    api_key_manager = APIKeyManager(db_pool) if db_pool else None
    stripe_manager = StripeManager(
        api_key=os.getenv("STRIPE_SECRET_KEY", ""),
        webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET", ""),
        db_pool=db_pool
    ) if db_pool else None
    logger.info("Managers initialized", api_key_manager=bool(api_key_manager), stripe_manager=bool(stripe_manager))

    # Initialize data aggregator
    from src.data_sources.aggregator import init_aggregator, DataPriority
    from src.data_sources.polygon_source import PolygonSource
    from src.data_sources.alphavantage_source import AlphaVantageSource
    from src.data_sources.finnhub_source import FinnhubSource
    from src.data_sources.yfinance_source import YFinanceSource

    aggregator = init_aggregator(redis_client)

    # Register data sources with priorities
    sec_source = SECEdgarSource({
        "user_agent": os.getenv("SEC_USER_AGENT", "FinSight API/1.0 (contact@finsight.io)")
    })
    register_source(sec_source)

    # Polygon.io - Real-time data (PRIMARY for Pro+ tiers)
    if os.getenv("POLYGON_API_KEY"):
        polygon_source = PolygonSource({
            "api_key": os.getenv("POLYGON_API_KEY")
        })
        aggregator.register_source(polygon_source, DataPriority.PRIMARY)
        logger.info("Registered Polygon.io (real-time)")

    # Alpha Vantage - Historical + fundamentals (SECONDARY)
    if os.getenv("ALPHA_VANTAGE_API_KEY"):
        alphavantage_source = AlphaVantageSource({
            "api_key": os.getenv("ALPHA_VANTAGE_API_KEY")
        })
        aggregator.register_source(alphavantage_source, DataPriority.SECONDARY)
        logger.info("Registered Alpha Vantage (historical)")

    # Finnhub - News + sentiment (SECONDARY)
    if os.getenv("FINNHUB_API_KEY"):
        finnhub_source = FinnhubSource({
            "api_key": os.getenv("FINNHUB_API_KEY")
        })
        aggregator.register_source(finnhub_source, DataPriority.SECONDARY)
        logger.info("Registered Finnhub (news/sentiment)")

    # yfinance - Free tier fallback (FALLBACK)
    yfinance_source = YFinanceSource()
    aggregator.register_source(yfinance_source, DataPriority.FALLBACK)
    logger.info("Registered yfinance (free tier fallback)")

    logger.info("Data sources registered and aggregator initialized")

    # Inject dependencies into route modules
    from src.api import auth as auth_module
    from src.api import subscriptions as subs_module

    auth_module.set_dependencies(api_key_manager, db_pool)
    subs_module.set_dependencies(stripe_manager)
    logger.info("Route dependencies injected")

    # Configure middleware once dependencies are ready
    if not getattr(app.state, "middleware_configured", False):
        if api_key_manager:
            app.add_middleware(AuthMiddleware, api_key_manager=api_key_manager)
        else:
            logger.warning("Auth middleware not added (API key manager unavailable)")

        if redis_client:
            app.add_middleware(RateLimitMiddleware, redis_client=redis_client)
        else:
            logger.warning("Rate limiting middleware not added (Redis unavailable)")

        app.state.middleware_configured = True

    yield

    # Shutdown
    logger.info("Shutting down FinSight API")

    if db_pool:
        await db_pool.close()
    if redis_client:
        await redis_client.aclose()


# Create FastAPI app
app = FastAPI(
    title="FinSight API",
    description="Production-grade financial data API with AI-powered synthesis",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"]
)

# Add Prometheus metrics
Instrumentator().instrument(app).expose(app, include_in_schema=False)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(
        "Unhandled exception",
        exception=str(exc),
        path=request.url.path,
        method=request.method,
        exc_info=True
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An internal server error occurred",
            "request_id": getattr(request.state, "request_id", "unknown")
        }
    )


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "FinSight API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "pricing": "https://finsight.io/pricing"
    }


# Health check
@app.get("/health")
async def health():
    """Health check endpoint"""
    db_status = "ok"
    redis_status = "ok"

    try:
        if db_pool:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        else:
            db_status = "not_configured"
    except Exception as e:
        db_status = f"error: {e}"

    try:
        if redis_client:
            await redis_client.ping()
        else:
            redis_status = "not_configured"
    except Exception as e:
        redis_status = f"error: {e}"

    status = "healthy" if db_status == "ok" and redis_status == "ok" else "degraded"

    if db_status.startswith("error") or redis_status.startswith("error"):
        logger.error("Health check failed", database=db_status, redis=redis_status)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": db_status,
                "redis": redis_status
            }
        )

    return {
        "status": status,
        "database": db_status,
        "redis": redis_status,
        "version": "1.0.0"
    }


# Import and include routers
from src.api import metrics, auth, companies, subscriptions, answers, intelligence, market

# Note: Dependencies are injected during lifespan startup
# Middleware is added after lifespan completes via the lifespan context manager

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(market.router, prefix="/api/v1", tags=["Market Data"])
app.include_router(intelligence.router, prefix="/api/v1", tags=["AI Intelligence"])
app.include_router(answers.router, prefix="/api/v1", tags=["LLM-Ready Answers"])
app.include_router(metrics.router, prefix="/api/v1", tags=["Financial Metrics"])
app.include_router(companies.router, prefix="/api/v1", tags=["Companies"])
app.include_router(subscriptions.router, prefix="/api/v1", tags=["Billing"])


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    debug = os.getenv("DEBUG", "false").lower() == "true"

    uvicorn.run(
        "src.main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    )
