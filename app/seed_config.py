"""Idempotent creation of default configuration rows.

Called once on application start-up (and by tests) so that pricing, discounts
and advertising rules always exist in the database instead of being hard-coded
throughout the application.
"""

from decimal import Decimal

from app import constants as C
from app.extensions import db
from app.models import (
    AdvertisingConfig,
    CategoryCompetitionConfig,
    PricingConfig,
    PromotionLevel,
    RentalDiscount,
)

DEFAULT_DISCOUNTS = (
    (1, 1, Decimal("0.00")),
    (2, 3, Decimal("0.03")),
    (4, 6, Decimal("0.05")),
    (7, 13, Decimal("0.10")),
    (14, None, Decimal("0.15")),
)

DEFAULT_PROMOTION_LEVELS = (
    (C.PROMOTION_LEVEL_BASIC, 10, Decimal("1.0")),
    (C.PROMOTION_LEVEL_STANDARD, 25, Decimal("1.5")),
    (C.PROMOTION_LEVEL_PREMIUM, 50, Decimal("2.0")),
)

DEFAULT_COMPETITION_TIERS = (
    (0, 20, Decimal("1.0")),
    (21, 50, Decimal("1.25")),
    (51, 100, Decimal("1.5")),
    (101, None, Decimal("2.0")),
)


def ensure_default_config() -> None:
    if PricingConfig.query.first() is None:
        db.session.add(
            PricingConfig(
                borrower_service_fee_rate=Decimal("0.05"),
                lender_platform_fee_rate=Decimal("0.10"),
                currency=C.CURRENCY,
            )
        )

    if RentalDiscount.query.count() == 0:
        for minimum, maximum, rate in DEFAULT_DISCOUNTS:
            db.session.add(
                RentalDiscount(minimum_days=minimum, maximum_days=maximum, discount_rate=rate)
            )

    if AdvertisingConfig.query.first() is None:
        db.session.add(AdvertisingConfig(base_daily_price=Decimal("20.00")))

    if PromotionLevel.query.count() == 0:
        for name, weight, multiplier in DEFAULT_PROMOTION_LEVELS:
            db.session.add(
                PromotionLevel(
                    name=name, ranking_weight=weight, price_multiplier=multiplier, active=True
                )
            )

    if CategoryCompetitionConfig.query.count() == 0:
        for minimum, maximum, multiplier in DEFAULT_COMPETITION_TIERS:
            db.session.add(
                CategoryCompetitionConfig(
                    minimum_listings=minimum,
                    maximum_listings=maximum,
                    competition_multiplier=multiplier,
                )
            )

    db.session.commit()
