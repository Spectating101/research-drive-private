"""
Rate Limiting Middleware for FinSight
Tier-based rate limiting with Redis backend
"""

import structlog
from datetime import datetime
from typing import Optional
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import redis.asyncio as redis

from src.models.user import PricingTier, TIER_LIMITS

logger = structlog.get_logger(__name__)


class RateLimiter:
    """Redis-backed rate limiter with tier-based limits"""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def check_rate_limit(
        self,
        user_id: str,
        tier: PricingTier,
        endpoint: str
    ) -> tuple[bool, int, int]:
        """
        Check if request is within rate limit

        Args:
            user_id: User ID
            tier: Pricing tier
            endpoint: API endpoint

        Returns:
            (allowed, remaining, reset_seconds)
        """
        # Get tier limits
        limit = TIER_LIMITS[tier]["rate_limit_per_minute"]

        # Redis key: rate:user_id:minute_timestamp
        now = datetime.utcnow()
        minute = now.strftime("%Y%m%d%H%M")
        key = f"rate:{user_id}:{minute}"

        # Increment counter
        current = await self.redis.incr(key)

        # Set expiration on first request of the minute
        if current == 1:
            await self.redis.expire(key, 60)

        # Calculate remaining
        remaining = max(0, limit - current)

        # Check if over limit
        allowed = current <= limit

        # Time until reset (seconds remaining in current minute)
        reset_seconds = 60 - now.second

        if not allowed:
            logger.warning(
                "Rate limit exceeded",
                user_id=user_id,
                tier=tier.value,
                limit=limit,
                current=current,
                endpoint=endpoint
            )

        return allowed, remaining, reset_seconds

    async def check_monthly_limit(
        self,
        user_id: str,
        tier: PricingTier,
        api_calls_this_month: int
    ) -> tuple[bool, int]:
        """
        Check monthly API call limit

        Args:
            user_id: User ID
            tier: Pricing tier
            api_calls_this_month: Current month's usage

        Returns:
            (allowed, remaining)
        """
        monthly_limit = TIER_LIMITS[tier]["api_calls_per_month"]

        # Enterprise = unlimited
        if monthly_limit == -1:
            return True, -1

        remaining = max(0, monthly_limit - api_calls_this_month)
        allowed = api_calls_this_month < monthly_limit

        if not allowed:
            logger.warning(
                "Monthly limit exceeded",
                user_id=user_id,
                tier=tier.value,
                limit=monthly_limit,
                current=api_calls_this_month
            )

        return allowed, remaining


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce rate limits"""

    def __init__(self, app, redis_client: redis.Redis):
        super().__init__(app)
        self.limiter = RateLimiter(redis_client)

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks and docs
        if request.url.path in ["/", "/health", "/docs", "/openapi.json"]:
            return await call_next(request)

        # Get user and tier from request state (set by auth middleware)
        user = getattr(request.state, "user", None)
        api_key = getattr(request.state, "api_key", None)

        if not user or not api_key:
            # Not authenticated, will be caught by auth middleware
            return await call_next(request)

        # Check per-minute rate limit
        allowed, remaining, reset_seconds = await self.limiter.check_rate_limit(
            user.user_id,
            user.tier,
            request.url.path
        )

        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded. Max {TIER_LIMITS[user.tier]['rate_limit_per_minute']} requests/minute for {user.tier.value} tier.",
                    "retry_after": reset_seconds,
                    "upgrade_url": "https://finsight.io/pricing"
                },
                headers={
                    "X-RateLimit-Limit": str(TIER_LIMITS[user.tier]["rate_limit_per_minute"]),
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Reset": str(reset_seconds),
                    "Retry-After": str(reset_seconds)
                }
            )

        # Check monthly limit
        monthly_allowed, monthly_remaining = await self.limiter.check_monthly_limit(
            user.user_id,
            user.tier,
            user.api_calls_this_month
        )

        if not monthly_allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "monthly_limit_exceeded",
                    "message": f"Monthly API call limit exceeded. Limit: {TIER_LIMITS[user.tier]['api_calls_per_month']} for {user.tier.value} tier.",
                    "upgrade_url": "https://finsight.io/pricing"
                },
                headers={
                    "X-Monthly-Limit": str(TIER_LIMITS[user.tier]["api_calls_per_month"]),
                    "X-Monthly-Remaining": str(monthly_remaining)
                }
            )

        # Add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(TIER_LIMITS[user.tier]["rate_limit_per_minute"])
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-Monthly-Limit"] = str(TIER_LIMITS[user.tier]["api_calls_per_month"])
        response.headers["X-Monthly-Remaining"] = str(monthly_remaining)

        return response
