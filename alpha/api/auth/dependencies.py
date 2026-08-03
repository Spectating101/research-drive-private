"""
Reusable authentication dependencies for FastAPI routes.
Centralizes user lookup from request state and tier enforcement.
"""

from functools import wraps
from typing import Callable, Awaitable

from fastapi import Depends, HTTPException, Request

from src.models.user import PricingTier, User


_TIER_ORDER = {
    PricingTier.FREE: 0,
    PricingTier.STARTER: 1,
    PricingTier.PROFESSIONAL: 2,
    PricingTier.ENTERPRISE: 3,
}


async def get_current_user(request: Request) -> User:
    """
    Retrieve the authenticated user injected by AuthMiddleware.

    Raises:
        HTTPException: 401 if no authenticated user is present.
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "authentication_required",
                "message": "Valid API key required",
            },
        )
    return user


def require_tier(min_tier: PricingTier) -> Callable[[User], Awaitable[User]]:
    """
    Dependency factory enforcing minimum pricing tier.

    Usage:
        @router.get("/path")
        async def route(user: User = Depends(require_tier(PricingTier.STARTER))):
            ...
    """

    async def dependency(user: User = Depends(get_current_user)) -> User:
        if _TIER_ORDER[user.tier] < _TIER_ORDER[min_tier]:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "feature_not_available",
                    "message": f"{min_tier.value.title()} tier required",
                    "upgrade_url": "https://finsight.io/pricing",
                },
            )
        return user

    return dependency
