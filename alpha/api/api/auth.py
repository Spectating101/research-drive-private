"""
Authentication and API Key Management Routes
"""

import secrets
import structlog
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List

from src.auth.api_keys import APIKeyManager
from src.models.user import User, APIKey, PricingTier, UserStatus

logger = structlog.get_logger(__name__)
router = APIRouter()

# This will be injected by dependency
_api_key_manager: Optional[APIKeyManager] = None
_db_pool = None


def set_dependencies(api_key_manager: APIKeyManager, db_pool):
    """Set global dependencies (called from main.py after startup)"""
    global _api_key_manager, _db_pool
    _api_key_manager = api_key_manager
    _db_pool = db_pool


def get_api_key_manager() -> APIKeyManager:
    """Dependency to get API key manager"""
    if _api_key_manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return _api_key_manager


class RegisterRequest(BaseModel):
    """User registration request"""
    email: EmailStr
    company_name: Optional[str] = None
    website: Optional[str] = None


class RegisterResponse(BaseModel):
    """User registration response"""
    user_id: str
    email: str
    tier: str
    api_key: str  # Full key shown ONCE
    key_prefix: str
    message: str


class CreateKeyRequest(BaseModel):
    """Request to create a new API key"""
    name: str = Field(default="Default Key", description="Name for this API key")
    test_mode: bool = Field(default=False, description="Create a test mode key")
    expires_days: Optional[int] = Field(None, description="Days until expiration")


class CreateKeyResponse(BaseModel):
    """Response with new API key"""
    key_id: str
    api_key: str  # Full key shown ONCE
    key_prefix: str
    name: str
    test_mode: bool
    created_at: datetime
    message: str


class ListKeysResponse(BaseModel):
    """Response listing user's API keys"""
    key_id: str
    key_prefix: str
    name: str
    is_active: bool
    is_test_mode: bool
    total_calls: int
    last_used_at: Optional[datetime]
    created_at: datetime
    expires_at: Optional[datetime]


async def get_current_user_from_header(
    authorization: str = Header(..., description="Bearer token or API key"),
    manager: APIKeyManager = Depends(get_api_key_manager)
) -> tuple[User, APIKey]:
    """Extract and validate API key from Authorization header"""

    # Support both "Bearer fsk_xxx" and "fsk_xxx" formats
    key = authorization
    if authorization.startswith("Bearer "):
        key = authorization[7:]

    result = await manager.validate_key(key)
    if not result:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_api_key",
                "message": "Invalid or expired API key"
            }
        )

    return result


@router.post("/register", response_model=RegisterResponse)
async def register_user(
    request: RegisterRequest,
    manager: APIKeyManager = Depends(get_api_key_manager)
):
    """
    Register a new user and get an API key

    **No authentication required**

    Creates a free tier account with 100 API calls/month.
    Returns an API key that must be saved (shown only once).
    """
    try:
        # Check if email already exists
        async with _db_pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT user_id FROM users WHERE email = $1",
                request.email
            )

            if existing:
                raise HTTPException(
                    status_code=409,
                    detail="Email already registered"
                )

            # Create user
            user_id = f"user_{secrets.token_urlsafe(16)}"
            await conn.execute(
                """
                INSERT INTO users (
                    user_id, email, company_name, website,
                    tier, status, api_calls_limit, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                user_id,
                request.email,
                request.company_name,
                request.website,
                PricingTier.FREE.value,
                UserStatus.ACTIVE.value,
                100,  # Free tier limit
                datetime.utcnow()
            )

        # Create API key
        full_key, api_key = await manager.create_api_key(
            user_id=user_id,
            name="Default Key"
        )

        logger.info(
            "User registered",
            user_id=user_id,
            email=request.email,
            tier="free"
        )

        return RegisterResponse(
            user_id=user_id,
            email=request.email,
            tier=PricingTier.FREE.value,
            api_key=full_key,
            key_prefix=api_key.key_prefix,
            message="Account created successfully. Save your API key - it won't be shown again!"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Registration failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Registration failed"
        )


@router.post("/keys", response_model=CreateKeyResponse)
async def create_api_key(
    request: CreateKeyRequest,
    auth: tuple[User, APIKey] = Depends(get_current_user_from_header),
    manager: APIKeyManager = Depends(get_api_key_manager)
):
    """
    Create a new API key

    **Authentication required**

    Creates an additional API key for your account.
    Some tiers limit the number of keys you can create.
    """
    user, _ = auth

    try:
        # Check key limit for tier
        from src.models.user import TIER_LIMITS
        max_keys = TIER_LIMITS[user.tier]["max_api_keys"]

        if max_keys != -1:  # -1 = unlimited
            existing_keys = await manager.list_user_keys(user.user_id)
            active_keys = [k for k in existing_keys if k.is_active]

            if len(active_keys) >= max_keys:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "key_limit_reached",
                        "message": f"Your {user.tier.value} tier allows {max_keys} active API keys",
                        "upgrade_url": "https://finsight.io/pricing"
                    }
                )

        # Create new key
        full_key, api_key = await manager.create_api_key(
            user_id=user.user_id,
            name=request.name,
            test_mode=request.test_mode,
            expires_days=request.expires_days
        )

        logger.info(
            "API key created",
            user_id=user.user_id,
            key_id=api_key.key_id,
            test_mode=request.test_mode
        )

        return CreateKeyResponse(
            key_id=api_key.key_id,
            api_key=full_key,
            key_prefix=api_key.key_prefix,
            name=api_key.name,
            test_mode=api_key.is_test_mode,
            created_at=api_key.created_at,
            message="API key created successfully. Save it - it won't be shown again!"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create API key", user_id=user.user_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to create API key"
        )


@router.get("/keys", response_model=List[ListKeysResponse])
async def list_api_keys(
    auth: tuple[User, APIKey] = Depends(get_current_user_from_header),
    manager: APIKeyManager = Depends(get_api_key_manager)
):
    """
    List all API keys for your account

    **Authentication required**

    Returns all API keys (active and revoked) with usage statistics.
    """
    user, _ = auth

    try:
        keys = await manager.list_user_keys(user.user_id)

        return [
            ListKeysResponse(
                key_id=k.key_id,
                key_prefix=k.key_prefix,
                name=k.name,
                is_active=k.is_active,
                is_test_mode=k.is_test_mode,
                total_calls=k.total_calls,
                last_used_at=k.last_used_at,
                created_at=k.created_at,
                expires_at=k.expires_at
            )
            for k in keys
        ]

    except Exception as e:
        logger.error("Failed to list keys", user_id=user.user_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to list API keys"
        )


@router.delete("/keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    auth: tuple[User, APIKey] = Depends(get_current_user_from_header),
    manager: APIKeyManager = Depends(get_api_key_manager)
):
    """
    Revoke an API key

    **Authentication required**

    Permanently revokes an API key. This cannot be undone.
    """
    user, _ = auth

    try:
        success = await manager.revoke_key(key_id, user.user_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail="API key not found"
            )

        return {
            "success": True,
            "message": "API key revoked successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to revoke key", user_id=user.user_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to revoke API key"
        )


@router.get("/me")
async def get_current_user_info(
    auth: tuple[User, APIKey] = Depends(get_current_user_from_header)
):
    """
    Get current user information

    **Authentication required**

    Returns your account details, usage, and limits.
    """
    user, api_key = auth

    from src.models.user import TIER_LIMITS
    limits = TIER_LIMITS[user.tier]

    return {
        "user_id": user.user_id,
        "email": user.email,
        "tier": user.tier.value,
        "status": user.status.value,
        "usage": {
            "api_calls_this_month": user.api_calls_this_month,
            "api_calls_limit": user.api_calls_limit,
            "remaining": user.api_calls_limit - user.api_calls_this_month if user.api_calls_limit != -1 else -1
        },
        "limits": {
            "rate_limit_per_minute": limits["rate_limit_per_minute"],
            "max_api_keys": limits["max_api_keys"],
            "data_sources": limits["data_sources"],
            "features": limits["features"]
        },
        "current_key": {
            "key_prefix": api_key.key_prefix,
            "name": api_key.name,
            "total_calls": api_key.total_calls
        }
    }
