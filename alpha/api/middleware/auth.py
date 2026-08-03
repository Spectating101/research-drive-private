"""
Authentication Middleware for FinSight
Validates API keys and attaches user context to requests
"""

import structlog
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from src.auth.api_keys import APIKeyManager

logger = structlog.get_logger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to authenticate API requests"""

    def __init__(self, app, api_key_manager: APIKeyManager):
        super().__init__(app)
        self.key_manager = api_key_manager

    async def dispatch(self, request: Request, call_next):
        # Skip auth for public endpoints
        public_paths = [
            "/",
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/api/v1/auth/register",
            "/api/v1/pricing",
            "/api/v1/webhooks/stripe",
            "/api/v1/metrics/available",
            "/api/v1/answers/available",
            "/metrics"  # Prometheus metrics
        ]

        if request.url.path in public_paths or request.url.path.startswith("/static"):
            return await call_next(request)

        if not self.key_manager:
            logger.error("Auth middleware not initialized")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "auth_unavailable",
                    "message": "Authentication service not initialized"
                }
            )

        # Extract API key from header
        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")

        if not api_key:
            logger.warning("Missing API key", path=request.url.path)
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "missing_api_key",
                    "message": "API key required. Include 'X-API-Key' header or 'Authorization: Bearer <key>' header.",
                    "docs": "https://docs.finsight.io/authentication"
                }
            )

        # Validate API key
        result = await self.key_manager.validate_key(api_key)

        if not result:
            logger.warning("Invalid API key", key_prefix=api_key[:12])
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "invalid_api_key",
                    "message": "Invalid or expired API key.",
                    "docs": "https://docs.finsight.io/authentication"
                }
            )

        user, api_key_obj = result

        # Attach user and key to request state
        request.state.user = user
        request.state.api_key = api_key_obj

        logger.debug(
            "Request authenticated",
            user_id=user.user_id,
            tier=user.tier.value,
            endpoint=request.url.path
        )

        return await call_next(request)
