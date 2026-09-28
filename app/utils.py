"""Small shared helpers: money formatting and Jinja registration."""

from decimal import Decimal, ROUND_HALF_UP

from app import constants as C

TWO_PLACES = Decimal("0.01")


def money(value) -> Decimal:
    """Round any numeric value to 2 decimal places using HALF_UP."""
    if value is None:
        value = 0
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def format_thb(value, with_symbol: bool = True) -> str:
    """Format a value as Thai Baht, e.g. ฿1,250.00"""
    amount = money(value)
    text = f"{amount:,.2f}"
    if with_symbol:
        return f"{C.CURRENCY_SYMBOL}{text}"
    return text


def format_thb_signed(value) -> str:
    amount = money(value)
    if amount < 0:
        return f"-{C.CURRENCY_SYMBOL}{abs(amount):,.2f}"
    return f"{C.CURRENCY_SYMBOL}{amount:,.2f}"


def format_percent(rate) -> str:
    """Format a decimal rate (0.10) as a percentage string (10%)."""
    text = format(to_decimal(rate) * 100, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text or '0'}%"


def register_jinja_helpers(app) -> None:
    from app import constants as constants  # local import to avoid cycles

    app.jinja_env.globals.update(
        thb=format_thb,
        thb_signed=format_thb_signed,
        pct=format_percent,
        CATEGORIES=constants.CATEGORIES,
        RENTAL_STATUS_LABELS=constants.RENTAL_STATUS_LABELS,
        ITEM_STATUS_LABELS=constants.ITEM_STATUS_LABELS,
        AD_STATUS_LABELS=constants.AD_STATUS_LABELS,
        TRANSACTION_STATUS_LABELS=constants.TRANSACTION_STATUS_LABELS,
        CURRENCY_SYMBOL=constants.CURRENCY_SYMBOL,
    )
