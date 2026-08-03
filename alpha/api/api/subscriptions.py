"""
Subscription and Billing Routes
Stripe integration for upgrades/downgrades
"""

import structlog
from fastapi import APIRouter, HTTPException, Depends, Request, Header
from pydantic import BaseModel
from typing import Optional

from src.billing.stripe_integration import StripeManager
from src.models.user import User, APIKey, PricingTier

logger = structlog.get_logger(__name__)
router = APIRouter()

# Global dependencies (injected from main.py)
_stripe_manager: Optional[StripeManager] = None


def set_dependencies(stripe_manager: StripeManager):
    """Set global dependencies"""
    global _stripe_manager
    _stripe_manager = stripe_manager


def get_stripe_manager() -> StripeManager:
    """Dependency to get Stripe manager"""
    if _stripe_manager is None:
        raise HTTPException(status_code=503, detail="Billing service not initialized")
    return _stripe_manager


async def get_current_user_from_header(
    request: Request
) -> tuple[User, APIKey]:
    """Get authenticated user from middleware-injected request state"""
    user = getattr(request.state, "user", None)
    api_key = getattr(request.state, "api_key", None)

    if not user or not api_key:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )

    return user, api_key


class CreateCheckoutRequest(BaseModel):
    """Request to create Stripe checkout session"""
    tier: PricingTier
    success_url: str
    cancel_url: str


class CreateCheckoutResponse(BaseModel):
    """Response with Stripe checkout URL"""
    checkout_url: str
    session_id: str


class SubscriptionInfoResponse(BaseModel):
    """Current subscription information"""
    user_id: str
    tier: str
    status: str
    api_calls_this_month: int
    api_calls_limit: int
    stripe_subscription_id: Optional[str]
    billing_period_start: Optional[str]
    billing_period_end: Optional[str]


@router.get("/subscription")
async def get_subscription_info(
    auth: tuple[User, APIKey] = Depends(get_current_user_from_header)
):
    """
    Get current subscription information

    **Authentication required**

    Returns your current tier, usage, and billing period.
    """
    user, _ = auth

    return SubscriptionInfoResponse(
        user_id=user.user_id,
        tier=user.tier.value,
        status=user.status.value,
        api_calls_this_month=user.api_calls_this_month,
        api_calls_limit=user.api_calls_limit,
        stripe_subscription_id=user.stripe_subscription_id,
        billing_period_start=user.billing_period_start.isoformat() if user.billing_period_start else None,
        billing_period_end=user.billing_period_end.isoformat() if user.billing_period_end else None
    )


@router.post("/subscription/checkout", response_model=CreateCheckoutResponse)
async def create_checkout_session(
    request: CreateCheckoutRequest,
    auth: tuple[User, APIKey] = Depends(get_current_user_from_header),
    stripe_mgr: StripeManager = Depends(get_stripe_manager)
):
    """
    Create Stripe checkout session for upgrading

    **Authentication required**

    Creates a Stripe checkout session for upgrading to a paid tier.
    Redirects user to Stripe's hosted checkout page.
    """
    user, _ = auth

    try:
        # Validate tier upgrade
        if request.tier == PricingTier.FREE:
            raise HTTPException(
                status_code=400,
                detail="Cannot create checkout for free tier"
            )

        if user.tier != PricingTier.FREE and user.stripe_subscription_id:
            raise HTTPException(
                status_code=400,
                detail="Use /subscription/upgrade to change existing subscription"
            )

        # Create Stripe checkout session
        import stripe
        from src.models.user import STRIPE_PRICE_IDS

        # Get or create Stripe customer
        customer_id = user.stripe_customer_id
        if not customer_id:
            customer_id = await stripe_mgr.create_customer(
                user_id=user.user_id,
                email=user.email
            )

        # Create checkout session
        price_id = STRIPE_PRICE_IDS[request.tier]
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{
                "price": price_id,
                "quantity": 1
            }],
            mode="subscription",
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            metadata={
                "user_id": user.user_id,
                "tier": request.tier.value
            }
        )

        logger.info(
            "Checkout session created",
            user_id=user.user_id,
            tier=request.tier.value,
            session_id=session.id
        )

        return CreateCheckoutResponse(
            checkout_url=session.url,
            session_id=session.id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create checkout", user_id=user.user_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to create checkout session"
        )


@router.post("/subscription/cancel")
async def cancel_subscription(
    auth: tuple[User, APIKey] = Depends(get_current_user_from_header),
    stripe_mgr: StripeManager = Depends(get_stripe_manager)
):
    """
    Cancel current subscription

    **Authentication required**

    Cancels your subscription at the end of the billing period.
    You'll be downgraded to free tier when the period ends.
    """
    user, _ = auth

    try:
        if user.tier == PricingTier.FREE:
            raise HTTPException(
                status_code=400,
                detail="No active subscription to cancel"
            )

        success = await stripe_mgr.cancel_subscription(user.user_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail="No active subscription found"
            )

        return {
            "success": True,
            "message": "Subscription will be cancelled at end of billing period"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to cancel subscription", user_id=user.user_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to cancel subscription"
        )


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="stripe-signature"),
    stripe_mgr: StripeManager = Depends(get_stripe_manager)
):
    """
    Stripe webhook endpoint

    **No authentication** (verified by Stripe signature)

    Handles Stripe events:
    - subscription.created
    - subscription.updated
    - subscription.deleted
    - invoice.payment_succeeded
    - invoice.payment_failed
    """
    try:
        # Get raw body
        payload = await request.body()

        # Process webhook
        result = await stripe_mgr.handle_webhook(payload, stripe_signature)

        logger.info("Webhook processed", event_type=result.get("event_type"))

        return {"success": True}

    except Exception as e:
        logger.error("Webhook processing failed", error=str(e))
        raise HTTPException(
            status_code=400,
            detail="Webhook processing failed"
        )


@router.get("/pricing")
async def get_pricing_info():
    """
    Get pricing tier information

    **No authentication required**

    Returns all available pricing tiers with features and limits.
    """
    from src.models.user import TIER_LIMITS

    return {
        "tiers": {
            "free": {
                "price": "$0/month",
                "limits": TIER_LIMITS[PricingTier.FREE]
            },
            "starter": {
                "price": "$49/month",
                "limits": TIER_LIMITS[PricingTier.STARTER]
            },
            "professional": {
                "price": "$199/month",
                "limits": TIER_LIMITS[PricingTier.PROFESSIONAL]
            },
            "enterprise": {
                "price": "$999/month",
                "limits": TIER_LIMITS[PricingTier.ENTERPRISE]
            }
        },
        "features_by_tier": {
            "free": ["SEC EDGAR data", "100 API calls/month", "Basic metrics"],
            "starter": ["Yahoo Finance", "1K API calls/month", "TTM calculations"],
            "professional": ["Alpha Vantage", "10K calls/month", "AI synthesis", "Webhooks"],
            "enterprise": ["Unlimited calls", "Priority support", "SLA", "Custom metrics"]
        }
    }
