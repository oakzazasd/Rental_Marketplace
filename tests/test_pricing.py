"""Rental pricing: discounts, borrower/lender fees, deposit separation."""

from decimal import Decimal

import pytest

from app.services.pricing import calculate_rental_price, get_discount_rate

CASES = [
    # days, discount rate, expected base, subtotal, borrower fee, borrower total,
    # lender fee, lender payout, platform revenue
    (1, "0.00", "100.00", "100.00", "5.00", "105.00", "10.00", "90.00", "15.00"),
    (2, "0.03", "200.00", "194.00", "9.70", "203.70", "19.40", "174.60", "29.10"),
    (3, "0.03", "300.00", "291.00", "14.55", "305.55", "29.10", "261.90", "43.65"),
    (4, "0.05", "400.00", "380.00", "19.00", "399.00", "38.00", "342.00", "57.00"),
    (7, "0.10", "700.00", "630.00", "31.50", "661.50", "63.00", "567.00", "94.50"),
    (14, "0.15", "1400.00", "1190.00", "59.50", "1249.50", "119.00", "1071.00", "178.50"),
    (30, "0.15", "3000.00", "2550.00", "127.50", "2677.50", "255.00", "2295.00", "382.50"),
]


@pytest.mark.parametrize(
    "days,rate,base,subtotal,fee,pay,lender_fee,payout,revenue", CASES
)
def test_price_breakdown(app_ctx, days, rate, base, subtotal, fee, pay, lender_fee, payout,
                         revenue):
    result = calculate_rental_price(Decimal("100.00"), days, deposit=Decimal("0.00"))
    assert result.discount_rate == Decimal(rate)
    assert result.base_amount == Decimal(base)
    assert result.discount_amount == money(base, rate)
    assert result.rental_subtotal == Decimal(subtotal)
    assert result.borrower_service_fee == Decimal(fee)
    assert result.borrower_total == Decimal(pay)
    assert result.lender_platform_fee == Decimal(lender_fee)
    assert result.lender_payout == Decimal(payout)
    assert result.platform_revenue == Decimal(revenue)


def money(base: str, rate: str) -> Decimal:
    value = Decimal(base) * Decimal(rate)
    return value.quantize(Decimal("0.01"))


def test_spec_example_exactly(app_ctx):
    result = calculate_rental_price(Decimal("100.00"), 7, deposit=Decimal("500.00"))
    assert result.base_amount == Decimal("700.00")
    assert result.discount_amount == Decimal("70.00")
    assert result.rental_subtotal == Decimal("630.00")
    assert result.borrower_service_fee == Decimal("31.50")
    assert result.borrower_total == Decimal("661.50")
    assert result.lender_platform_fee == Decimal("63.00")
    assert result.lender_payout == Decimal("567.00")
    assert result.platform_revenue == Decimal("94.50")
    # deposit is separate from every commission calculation
    assert result.deposit == Decimal("500.00")
    assert result.amount_required == Decimal("1161.50")
    assert result.rental_subtotal + Decimal("0") != result.amount_required


def test_fees_default_to_config(app_ctx):
    from app.models import PricingConfig

    config = PricingConfig.query.first()
    assert config.borrower_service_fee_rate == Decimal("0.0500")
    assert config.lender_platform_fee_rate == Decimal("0.1000")

    result = calculate_rental_price(Decimal("1000.00"), 1)
    assert result.borrower_fee_rate == Decimal("0.0500")
    assert result.lender_fee_rate == Decimal("0.1000")


def test_discount_tiers_from_database(app_ctx):
    assert get_discount_rate(1) == Decimal("0.0000")
    assert get_discount_rate(2) == Decimal("0.0300")
    assert get_discount_rate(3) == Decimal("0.0300")
    assert get_discount_rate(6) == Decimal("0.0500")
    assert get_discount_rate(7) == Decimal("0.1000")
    assert get_discount_rate(13) == Decimal("0.1000")
    assert get_discount_rate(14) == Decimal("0.1500")
    assert get_discount_rate(99) == Decimal("0.1500")


def test_rounding_half_up(app_ctx):
    # 0.05 * 630 = 31.5 exactly; use an amount that needs rounding
    result = calculate_rental_price(Decimal("9.99"), 7)  # base 69.93, -10% = 62.94 (6.993 -> 6.99)
    assert result.base_amount == Decimal("69.93")
    assert result.discount_amount == Decimal("6.99")
    assert result.rental_subtotal == Decimal("62.94")
    assert result.borrower_service_fee == Decimal("3.15")  # 3.147 -> 3.15
    assert result.lender_platform_fee == Decimal("6.29")   # 6.294 -> 6.29
    assert result.platform_revenue == Decimal("9.44")


def test_rejects_invalid_day_count(app_ctx):
    with pytest.raises(ValueError):
        calculate_rental_price(Decimal("100.00"), 0)
