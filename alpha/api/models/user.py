"""
User and API Key models for FinSight
Clean separation from Cite-Agent
"""

import os
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class PricingTier(str, Enum):
    """Pricing tiers for FinSight API"""
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class UserStatus(str, Enum):
    """User account status"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    TRIAL = "trial"


class User(BaseModel):
    """FinSight user model"""
    user_id: str
    email: EmailStr
    company_name: Optional[str] = None
    tier: PricingTier = PricingTier.FREE
    status: UserStatus = UserStatus.ACTIVE

    # Usage tracking
    api_calls_this_month: int = 0
    api_calls_limit: int = 100  # Default free tier

    # Billing
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    billing_period_start: Optional[datetime] = None
    billing_period_end: Optional[datetime] = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_api_call: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class APIKey(BaseModel):
    """API key model with usage tracking"""
    key_id: str
    user_id: str
    key_hash: str  # Never store plaintext keys
    key_prefix: str  # First 8 chars for display (e.g., "fsk_1234...")

    name: str = "Default Key"

    # Status
    is_active: bool = True
    is_test_mode: bool = False

    # Usage tracking
    total_calls: int = 0
    calls_this_month: int = 0
    last_used_at: Optional[datetime] = None

    # Security
    allowed_ips: Optional[list[str]] = None  # IP whitelist
    allowed_domains: Optional[list[str]] = None  # CORS domains

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UsageRecord(BaseModel):
    """Track API usage for billing"""
    record_id: str
    user_id: str
    key_id: str

    endpoint: str
    method: str
    status_code: int

    # Cost calculation
    credits_used: int = 1  # Different endpoints cost different credits

    # Metadata
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    response_time_ms: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


# Pricing tier limits (optimized for monetization)
TIER_LIMITS = {
    PricingTier.FREE: {
        "api_calls_per_month": 50,  # Limited for lead gen only
        "rate_limit_per_minute": 5,  # Very conservative
        "max_api_keys": 1,
        "data_sources": ["sec"],  # Only SEC EDGAR
        "features": ["basic_metrics"],  # /metrics only, no /answers
        "price_monthly": 0,
    },
    PricingTier.STARTER: {
        "api_calls_per_month": 2000,  # Increased value
        "rate_limit_per_minute": 30,
        "max_api_keys": 3,
        "data_sources": ["sec", "yahoo"],
        "features": ["basic_metrics", "llm_answers", "citations", "consistency_score"],
        "price_monthly": 49,  # $49/mo sweet spot
    },
    PricingTier.PROFESSIONAL: {
        "api_calls_per_month": 10000,
        "rate_limit_per_minute": 100,
        "max_api_keys": 10,
        "data_sources": ["sec", "yahoo", "alpha_vantage", "finnhub"],
        "features": ["all_metrics", "llm_answers", "ai_synthesis", "webhooks", "audit_logs"],
        "price_monthly": 199,  # $199/mo for serious users
        "sla_uptime": "99.9%",
        "sla_latency_p95": "300ms",
    },
    PricingTier.ENTERPRISE: {
        "api_calls_per_month": -1,  # Unlimited
        "rate_limit_per_minute": 500,
        "max_api_keys": -1,  # Unlimited
        "data_sources": ["all"],
        "features": ["all", "priority_support", "custom_metrics", "dedicated_instance"],
        "price_monthly": 999,  # $999/mo starting
        "sla_uptime": "99.95%",
        "sla_latency_p95": "200ms",
        "custom_contract": True,
    },
}


# Stripe price IDs (set these after creating products in Stripe Dashboard)
STRIPE_PRICE_IDS = {
    PricingTier.STARTER: os.getenv("STRIPE_PRICE_STARTER", "price_xxx_starter_monthly"),
    PricingTier.PROFESSIONAL: os.getenv("STRIPE_PRICE_PRO", "price_xxx_pro_monthly"),
    PricingTier.ENTERPRISE: os.getenv("STRIPE_PRICE_ENTERPRISE", "price_xxx_enterprise_monthly"),
}
