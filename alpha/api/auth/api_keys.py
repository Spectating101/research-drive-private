"""
API Key Management for FinSight
Secure key generation, validation, and usage tracking
"""

import secrets
import hashlib
import structlog
from datetime import datetime, timedelta
from typing import Optional, Tuple
import asyncpg

from src.models.user import APIKey, User, PricingTier, UserStatus

logger = structlog.get_logger(__name__)


class APIKeyManager:
    """Manages API key lifecycle and validation"""

    def __init__(self, db_pool: asyncpg.Pool):
        self.db = db_pool
        self.key_prefix = "fsk_"  # FinSight Key

    def generate_key(self) -> Tuple[str, str, str]:
        """
        Generate a new API key

        Returns:
            (key, key_hash, key_prefix)
            - key: Full key to show user ONCE (never stored)
            - key_hash: Hashed key to store in database
            - key_prefix: First 8 chars for display
        """
        # Generate 32-byte random key
        random_bytes = secrets.token_bytes(32)
        key_suffix = secrets.token_urlsafe(32)

        # Format: fsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
        full_key = f"{self.key_prefix}{key_suffix}"

        # Hash for storage (never store plaintext)
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()

        # Prefix for display (e.g., "fsk_Ab7d...")
        key_prefix = full_key[:12]

        return full_key, key_hash, key_prefix

    async def create_api_key(
        self,
        user_id: str,
        name: str = "Default Key",
        test_mode: bool = False,
        expires_days: Optional[int] = None
    ) -> Tuple[str, APIKey]:
        """
        Create a new API key for a user

        Args:
            user_id: User ID
            name: Key name for identification
            test_mode: Whether this is a test key
            expires_days: Optional expiration in days

        Returns:
            (full_key, api_key_object)
            IMPORTANT: full_key is only returned here, never stored
        """
        # Generate key
        full_key, key_hash, key_prefix = self.generate_key()

        # Generate key ID
        key_id = f"key_{secrets.token_urlsafe(16)}"

        # Calculate expiration
        expires_at = None
        if expires_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_days)

        # Store in database
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO api_keys (
                    key_id, user_id, key_hash, key_prefix, name,
                    is_test_mode, expires_at, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                key_id, user_id, key_hash, key_prefix, name,
                test_mode, expires_at, datetime.utcnow()
            )

        logger.info(
            "API key created",
            user_id=user_id,
            key_id=key_id,
            key_prefix=key_prefix,
            test_mode=test_mode
        )

        # Return key object (without sensitive data)
        api_key = APIKey(
            key_id=key_id,
            user_id=user_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=name,
            is_test_mode=test_mode,
            expires_at=expires_at,
            created_at=datetime.utcnow()
        )

        return full_key, api_key

    async def validate_key(self, key: str) -> Optional[Tuple[User, APIKey]]:
        """
        Validate an API key and return user + key info

        Args:
            key: Full API key from request header

        Returns:
            (User, APIKey) if valid, None if invalid
        """
        # Hash the provided key
        key_hash = hashlib.sha256(key.encode()).hexdigest()

        async with self.db.acquire() as conn:
            # Get key info
            key_row = await conn.fetchrow(
                """
                SELECT k.*, u.user_id, u.email, u.tier, u.status,
                       u.api_calls_this_month, u.api_calls_limit,
                       u.stripe_customer_id
                FROM api_keys k
                JOIN users u ON k.user_id = u.user_id
                WHERE k.key_hash = $1
                  AND k.is_active = true
                  AND u.status = 'active'
                  AND (k.expires_at IS NULL OR k.expires_at > $2)
                """,
                key_hash, datetime.utcnow()
            )

            if not key_row:
                logger.warning("Invalid API key attempt", key_prefix=key[:12])
                return None

            # Update last used timestamp
            await conn.execute(
                """
                UPDATE api_keys
                SET last_used_at = $1, total_calls = total_calls + 1
                WHERE key_id = $2
                """,
                datetime.utcnow(), key_row['key_id']
            )

            # Build user object
            user = User(
                user_id=key_row['user_id'],
                email=key_row['email'],
                tier=PricingTier(key_row['tier']),
                status=UserStatus(key_row['status']),
                api_calls_this_month=key_row['api_calls_this_month'],
                api_calls_limit=key_row['api_calls_limit'],
                stripe_customer_id=key_row['stripe_customer_id']
            )

            # Build API key object
            api_key = APIKey(
                key_id=key_row['key_id'],
                user_id=key_row['user_id'],
                key_hash=key_row['key_hash'],
                key_prefix=key_row['key_prefix'],
                name=key_row['name'],
                is_active=key_row['is_active'],
                is_test_mode=key_row['is_test_mode'],
                total_calls=key_row['total_calls'],
                last_used_at=key_row['last_used_at'],
                created_at=key_row['created_at'],
                expires_at=key_row['expires_at']
            )

            logger.debug(
                "API key validated",
                user_id=user.user_id,
                tier=user.tier.value,
                key_prefix=api_key.key_prefix
            )

            return user, api_key

    async def revoke_key(self, key_id: str, user_id: str) -> bool:
        """
        Revoke an API key

        Args:
            key_id: Key ID to revoke
            user_id: User ID (for authorization check)

        Returns:
            True if revoked, False if not found
        """
        async with self.db.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE api_keys
                SET is_active = false
                WHERE key_id = $1 AND user_id = $2
                """,
                key_id, user_id
            )

            if result == "UPDATE 1":
                logger.info("API key revoked", key_id=key_id, user_id=user_id)
                return True

            return False

    async def list_user_keys(self, user_id: str) -> list[APIKey]:
        """
        List all API keys for a user

        Args:
            user_id: User ID

        Returns:
            List of APIKey objects
        """
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT key_id, user_id, key_hash, key_prefix, name,
                       is_active, is_test_mode, total_calls, last_used_at,
                       created_at, expires_at
                FROM api_keys
                WHERE user_id = $1
                ORDER BY created_at DESC
                """,
                user_id
            )

            return [
                APIKey(
                    key_id=row['key_id'],
                    user_id=row['user_id'],
                    key_hash=row['key_hash'],
                    key_prefix=row['key_prefix'],
                    name=row['name'],
                    is_active=row['is_active'],
                    is_test_mode=row['is_test_mode'],
                    total_calls=row['total_calls'],
                    last_used_at=row['last_used_at'],
                    created_at=row['created_at'],
                    expires_at=row['expires_at']
                )
                for row in rows
            ]
