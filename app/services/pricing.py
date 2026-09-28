"""Centralised rental pricing calculations.

Every price shown anywhere in the application is produced by this module so
that the 5% borrower fee, 10% lender fee and long-term discount tiers are
never duplicated inside route handlers.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from app.extensions import db
from app.models import PricingConfig, RentalDiscount
from app.utils import money, to_decimal

DEFAULT_BORROWER_FEE_RATE = Decimal("0.05")
DEFAULT_LENDER_FEE_RATE = Decimal("0.10")


@dataclass(frozen=True)
class PriceBreakdown:
    daily_price: Decimal
    rental_days: int
    base_amount: Decimal
    discount_rate: Decimal
    discount_amount: Decimal
    rental_subtotal: Decimal
    borrower_fee_rate: Decimal
    borrower_service_fee: Decimal
    borrower_total: Decimal
    lender_fee_rate: Decimal
    lender_platform_fee: Decimal
    lender_payout: Decimal
    platform_revenue: Decimal
    deposit: Decimal = Decimal("0.00")
    amount_required: Decimal = Decimal("0.00")
    currency: str = "THB"

    def as_dict(self) -> dict:
        return {
            "daily_price": self.daily_price,
            "rental_days": self.rental_days,
            "base_amount": self.base_amount,
            "discount_rate": self.discount_rate,
            "discount_amount": self.discount_amount,
            "rental_subtotal": self.rental_subtotal,
            "borrower_fee_rate": self.borrower_fee_rate,
            "borrower_service_fee": self.borrower_service_fee,
            "borrower_total": self.borrower_total,
            "lender_fee_rate": self.lender_fee_rate,
            "lender_platform_fee": self.lender_platform_fee,
            "lender_payout": self.lender_payout,
            "platform_revenue": self.platform_revenue,
            "deposit": self.deposit,
            "amount_required": self.amount_required,
            "currency": self.currency,
        }


def get_pricing_config() -> PricingConfig:
    config = PricingConfig.query.first()
    if config is None:
        config = PricingConfig(
            borrower_service_fee_rate=DEFAULT_BORROWER_FEE_RATE,
            lender_platform_fee_rate=DEFAULT_LENDER_FEE_RATE,
        )
    return config


def get_discount_rate(rental_days: int) -> Decimal:
    """Return the configured long-term discount rate for a number of days."""
    if rental_days < 1:
        rental_days = 1
    tier = (
        RentalDiscount.query.filter(
            RentalDiscount.active.is_(True),
            RentalDiscount.minimum_days <= rental_days,
            db.or_(
                RentalDiscount.maximum_days.is_(None),
                RentalDiscount.maximum_days >= rental_days,
            ),
        )
        .order_by(RentalDiscount.minimum_days.desc())
        .first()
    )
    if tier is None:
        return Decimal("0")
    return to_decimal(tier.discount_rate)


def calculate_rental_price(
    daily_price,
    rental_days: int,
    borrower_fee_rate=None,
    lender_fee_rate=None,
    deposit=0,
    discount_rate=None,
) -> PriceBreakdown:
    """Calculate the full rental price breakdown using Decimal arithmetic.

    Returns base_amount, discount_rate, discount_amount, rental_subtotal,
    borrower_service_fee, borrower_total, lender_platform_fee, lender_payout
    and platform_revenue.
    """
    rental_days = int(rental_days)
    if rental_days < 1:
        raise ValueError("rental_days must be at least 1")

    daily = money(daily_price)
    deposit = money(deposit)
    config = get_pricing_config()

    if borrower_fee_rate is None:
        borrower_fee_rate = to_decimal(config.borrower_service_fee_rate)
    else:
        borrower_fee_rate = to_decimal(borrower_fee_rate)

    if lender_fee_rate is None:
        lender_fee_rate = to_decimal(config.lender_platform_fee_rate)
    else:
        lender_fee_rate = to_decimal(lender_fee_rate)

    if discount_rate is None:
        discount_rate = get_discount_rate(rental_days)
    else:
        discount_rate = to_decimal(discount_rate)

    base_amount = money(daily * rental_days)
    discount_amount = money(base_amount * discount_rate)
    rental_subtotal = money(base_amount - discount_amount)

    borrower_service_fee = money(rental_subtotal * borrower_fee_rate)
    borrower_total = money(rental_subtotal + borrower_service_fee)

    lender_platform_fee = money(rental_subtotal * lender_fee_rate)
    lender_payout = money(rental_subtotal - lender_platform_fee)

    platform_revenue = money(borrower_service_fee + lender_platform_fee)
    amount_required = money(borrower_total + deposit)

    return PriceBreakdown(
        daily_price=daily,
        rental_days=rental_days,
        base_amount=base_amount,
        discount_rate=discount_rate,
        discount_amount=discount_amount,
        rental_subtotal=rental_subtotal,
        borrower_fee_rate=borrower_fee_rate,
        borrower_service_fee=borrower_service_fee,
        borrower_total=borrower_total,
        lender_fee_rate=lender_fee_rate,
        lender_platform_fee=lender_platform_fee,
        lender_payout=lender_payout,
        platform_revenue=platform_revenue,
        deposit=deposit,
        amount_required=amount_required,
        currency=config.currency or "THB",
    )
