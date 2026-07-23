"""
Stripe Integration for FinSight
Handles subscriptions, webhooks, and usage tracking
"""

import stripe
import structlog
from typing import Dict, Any, Optional
from datetime import datetime
import asyncpg

from src.models.user import PricingTier, STRIPE_PRICE_IDS, TIER_LIMITS

logger = structlog.get_logger(__name__)


class StripeManager:
    """Manages Stripe billing operations"""

    def __init__(self, api_key: str, webhook_secret: str, db_pool: asyncpg.Pool):
        stripe.api_key = api_key
        self.webhook_secret = webhook_secret
        self.db = db_pool

    async def create_customer(
        self,
        user_id: str,
        email: str,
        company_name: Optional[str] = None
    ) -> str:
        """
        Create a Stripe customer

        Args:
            user_id: Internal user ID
            email: Customer email
            company_name: Optional company name

        Returns:
            Stripe customer ID
        """
        try:
            customer = stripe.Customer.create(
                email=email,
                metadata={
                    "user_id": user_id,
                    "company_name": company_name or ""
                }
            )

            # Store in database
            async with self.db.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE users
                    SET stripe_customer_id = $1, updated_at = $2
                    WHERE user_id = $3
                    """,
                    customer.id, datetime.utcnow(), user_id
                )

            logger.info("Stripe customer created", user_id=user_id, customer_id=customer.id)
            return customer.id

        except Exception as e:
            logger.error("Failed to create Stripe customer", user_id=user_id, error=str(e))
            raise

    async def create_subscription(
        self,
        user_id: str,
        tier: PricingTier,
        payment_method_id: str
    ) -> Dict[str, Any]:
        """
        Create a subscription for a user

        Args:
            user_id: User ID
            tier: Pricing tier
            payment_method_id: Stripe payment method ID

        Returns:
            Subscription info dict
        """
        try:
            # Get or create Stripe customer
            async with self.db.acquire() as conn:
                user = await conn.fetchrow(
                    "SELECT stripe_customer_id, email, company_name FROM users WHERE user_id = $1",
                    user_id
                )

            if not user:
                raise ValueError("User not found")

            customer_id = user["stripe_customer_id"]
            if not customer_id:
                customer_id = await self.create_customer(
                    user_id, user["email"], user["company_name"]
                )

            # Attach payment method to customer
            stripe.PaymentMethod.attach(payment_method_id, customer=customer_id)

            # Set as default payment method
            stripe.Customer.modify(
                customer_id,
                invoice_settings={"default_payment_method": payment_method_id}
            )

            # Create subscription
            price_id = STRIPE_PRICE_IDS[tier]
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{"price": price_id}],
                metadata={"user_id": user_id}
            )

            # Update user tier in database
            async with self.db.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE users
                    SET tier = $1,
                        stripe_subscription_id = $2,
                        billing_period_start = $3,
                        billing_period_end = $4,
                        api_calls_limit = $5,
                        status = 'active',
                        updated_at = $6
                    WHERE user_id = $7
                    """,
                    tier.value,
                    subscription.id,
                    datetime.fromtimestamp(subscription.current_period_start),
                    datetime.fromtimestamp(subscription.current_period_end),
                    TIER_LIMITS[tier]["api_calls_per_month"],
                    datetime.utcnow(),
                    user_id
                )

                # Log subscription change
                await conn.execute(
                    """
                    INSERT INTO subscription_history (user_id, old_tier, new_tier, stripe_subscription_id, change_reason)
                    VALUES ($1, 'free', $2, $3, 'upgrade')
                    """,
                    user_id, tier.value, subscription.id
                )

            logger.info(
                "Subscription created",
                user_id=user_id,
                tier=tier.value,
                subscription_id=subscription.id
            )

            return {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "current_period_end": subscription.current_period_end
            }

        except Exception as e:
            logger.error("Failed to create subscription", user_id=user_id, error=str(e))
            raise

    async def cancel_subscription(self, user_id: str) -> bool:
        """
        Cancel a user's subscription

        Args:
            user_id: User ID

        Returns:
            True if cancelled successfully
        """
        try:
            async with self.db.acquire() as conn:
                user = await conn.fetchrow(
                    "SELECT stripe_subscription_id, tier FROM users WHERE user_id = $1",
                    user_id
                )

            if not user or not user["stripe_subscription_id"]:
                logger.warning("No active subscription to cancel", user_id=user_id)
                return False

            # Cancel at period end (don't refund)
            stripe.Subscription.modify(
                user["stripe_subscription_id"],
                cancel_at_period_end=True
            )

            # Log cancellation
            async with self.db.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO subscription_history (user_id, old_tier, new_tier, stripe_subscription_id, change_reason)
                    VALUES ($1, $2, 'free', $3, 'cancelled')
                    """,
                    user_id, user["tier"], user["stripe_subscription_id"]
                )

            logger.info("Subscription cancelled", user_id=user_id)
            return True

        except Exception as e:
            logger.error("Failed to cancel subscription", user_id=user_id, error=str(e))
            return False

    async def handle_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """
        Handle Stripe webhook event

        Args:
            payload: Raw webhook payload
            signature: Stripe signature header

        Returns:
            Event processing result
        """
        try:
            # Verify webhook signature
            event = stripe.Webhook.construct_event(
                payload, signature, self.webhook_secret
            )

            # Store event for debugging
            async with self.db.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO webhook_events (event_id, event_type, payload)
                    VALUES ($1, $2, $3)
                    """,
                    event.id, event.type, event.to_dict()
                )

            # Handle different event types
            if event.type == "customer.subscription.created":
                await self._handle_subscription_created(event)
            elif event.type == "customer.subscription.updated":
                await self._handle_subscription_updated(event)
            elif event.type == "customer.subscription.deleted":
                await self._handle_subscription_deleted(event)
            elif event.type == "invoice.payment_succeeded":
                await self._handle_payment_succeeded(event)
            elif event.type == "invoice.payment_failed":
                await self._handle_payment_failed(event)

            # Mark as processed
            async with self.db.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE webhook_events
                    SET processed = true, processed_at = $1
                    WHERE event_id = $2
                    """,
                    datetime.utcnow(), event.id
                )

            logger.info("Webhook processed", event_type=event.type, event_id=event.id)
            return {"status": "success", "event_type": event.type}

        except Exception as e:
            logger.error("Webhook processing failed", error=str(e))

            # Store error
            async with self.db.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE webhook_events
                    SET processing_error = $1
                    WHERE event_id = $2
                    """,
                    str(e), event.id
                )

            raise

    async def _handle_subscription_created(self, event):
        """Handle subscription.created event"""
        subscription = event.data.object
        user_id = subscription.metadata.get("user_id")

        if not user_id:
            logger.warning("No user_id in subscription metadata", subscription_id=subscription.id)
            return

        logger.info("Subscription created webhook", user_id=user_id, subscription_id=subscription.id)

    async def _handle_subscription_updated(self, event):
        """Handle subscription.updated event"""
        subscription = event.data.object
        user_id = subscription.metadata.get("user_id")

        if not user_id:
            return

        # Update user's billing period
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE users
                SET billing_period_start = $1,
                    billing_period_end = $2,
                    updated_at = $3
                WHERE user_id = $4
                """,
                datetime.fromtimestamp(subscription.current_period_start),
                datetime.fromtimestamp(subscription.current_period_end),
                datetime.utcnow(),
                user_id
            )

    async def _handle_subscription_deleted(self, event):
        """Handle subscription.deleted event"""
        subscription = event.data.object
        user_id = subscription.metadata.get("user_id")

        if not user_id:
            return

        # Downgrade to free tier
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE users
                SET tier = 'free',
                    status = 'cancelled',
                    api_calls_limit = 100,
                    stripe_subscription_id = NULL,
                    updated_at = $1
                WHERE user_id = $2
                """,
                datetime.utcnow(),
                user_id
            )

            await conn.execute(
                """
                INSERT INTO subscription_history (user_id, old_tier, new_tier, change_reason)
                SELECT tier, 'free', 'subscription_ended'
                FROM users WHERE user_id = $1
                """,
                user_id
            )

        logger.info("User downgraded to free tier", user_id=user_id)

    async def _handle_payment_succeeded(self, event):
        """Handle successful payment"""
        invoice = event.data.object
        customer_id = invoice.customer

        # Reset monthly usage on successful payment
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE users
                SET api_calls_this_month = 0,
                    last_reset_at = $1
                WHERE stripe_customer_id = $2
                """,
                datetime.utcnow(),
                customer_id
            )

        logger.info("Payment succeeded, usage reset", customer_id=customer_id)

    async def _handle_payment_failed(self, event):
        """Handle failed payment"""
        invoice = event.data.object
        customer_id = invoice.customer

        # Suspend account after failed payment
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE users
                SET status = 'suspended'
                WHERE stripe_customer_id = $1
                """,
                customer_id
            )

        logger.warning("Payment failed, account suspended", customer_id=customer_id)
