"""Advertising / promoted listing calculations and lifecycle.

All advertising math lives here (never in routes):

    total_price = base_daily_price × competition_multiplier
                  × promotion_level_multiplier × duration_days

No real payment processing is implemented yet. Purchases create an
`Advertisement` record directly so a payment provider can be wired in later.
"""

from datetime import date, timedelta
from decimal import Decimal

from app import constants as C
from app.extensions import db
from app.models import (
    Advertisement,
    AdvertisingConfig,
    CategoryCompetitionConfig,
    Item,
    PromotionLevel,
    RentalRequest,
)
from app.utils import money, to_decimal


class AdvertisingError(Exception):
    """User facing advertising error."""


DEFAULT_BASE_DAILY_PRICE = Decimal("20.00")


def get_advertising_config() -> AdvertisingConfig:
    config = AdvertisingConfig.query.first()
    if config is None:
        config = AdvertisingConfig(base_daily_price=DEFAULT_BASE_DAILY_PRICE)
    return config


def get_promotion_level(name: str) -> PromotionLevel | None:
    if not name:
        return None
    return PromotionLevel.query.filter(
        PromotionLevel.name == str(name), PromotionLevel.active.is_(True)
    ).first()


def active_listing_count(category: str) -> int:
    """Number of active (currently listed, available) items in a category."""
    if not category:
        return 0
    return Item.query.filter(Item.category == category, Item.status == "available").count()


def competition_tier(listing_count: int) -> CategoryCompetitionConfig | None:
    return (
        CategoryCompetitionConfig.query.filter(
            CategoryCompetitionConfig.minimum_listings <= listing_count,
            db.or_(
                CategoryCompetitionConfig.maximum_listings.is_(None),
                CategoryCompetitionConfig.maximum_listings >= listing_count,
            ),
        )
        .order_by(CategoryCompetitionConfig.minimum_listings.desc())
        .first()
    )


def competition_label(listing_count: int) -> str:
    if listing_count <= 20:
        return "Low"
    if listing_count <= 50:
        return "Medium"
    if listing_count <= 100:
        return "High"
    return "Very High"


def calculate_ad_price(category: str, promotion_level: str, duration_days: int) -> dict:
    """Return the full advertising price breakdown for a promotion purchase."""
    duration_days = int(duration_days)
    if duration_days not in C.AD_DURATION_CHOICES:
        raise AdvertisingError(
            "Invalid duration. Choose one of: "
            + ", ".join(f"{d} day(s)" for d in C.AD_DURATION_CHOICES)
        )

    level = get_promotion_level(promotion_level)
    if level is None:
        raise AdvertisingError("Unknown promotion level.")

    base_price = money(get_advertising_config().base_daily_price or DEFAULT_BASE_DAILY_PRICE)
    listing_count = active_listing_count(category)

    tier = competition_tier(listing_count)
    competition_multiplier = to_decimal(tier.competition_multiplier) if tier else Decimal("1.0")
    level_multiplier = to_decimal(level.price_multiplier)

    daily_price = money(base_price * competition_multiplier * level_multiplier)
    total_price = money(daily_price * duration_days)

    return {
        "category": category,
        "base_price": base_price,
        "category_listing_count": listing_count,
        "competition_multiplier": competition_multiplier,
        "competition_level": competition_label(listing_count),
        "promotion_level": level.name,
        "promotion_level_multiplier": level_multiplier,
        "promotion_level_weight": level.ranking_weight,
        "daily_price": daily_price,
        "duration_days": duration_days,
        "total_price": total_price,
        "currency": C.CURRENCY,
    }


def create_advertisement(
    item: Item, owner_id: int, promotion_level: str, duration_days: int, start: date | None = None
) -> Advertisement:
    if item.status == "deleted":
        raise AdvertisingError("You cannot promote a deleted item.")
    if item.owner_id != owner_id:
        raise AdvertisingError("You can only promote your own items.")

    price = calculate_ad_price(item.category, promotion_level, duration_days)
    start_date = start or date.today()
    end_date = start_date + timedelta(days=duration_days - 1)

    advertisement = Advertisement(
        item_id=item.id,
        owner_id=owner_id,
        promotion_level=price["promotion_level"],
        start_date=start_date,
        end_date=end_date,
        daily_price=price["daily_price"],
        total_price=price["total_price"],
        status="active",
    )
    db.session.add(advertisement)
    db.session.flush()
    return advertisement


def cancel_advertisement(advertisement: Advertisement, owner_id: int) -> Advertisement:
    if advertisement.owner_id != owner_id:
        raise AdvertisingError("You can only cancel your own promotions.")
    if advertisement.status != "active":
        raise AdvertisingError("Only active promotions can be cancelled.")
    if advertisement.end_date < date.today():
        raise AdvertisingError("This promotion has already expired.")
    advertisement.status = "cancelled"
    db.session.flush()
    return advertisement


def sync_advertisements() -> None:
    """Mark promotions that ran out of time as expired."""
    today = date.today()
    running = Advertisement.query.filter(Advertisement.status == "active").all()
    changed = False
    for advertisement in running:
        if advertisement.end_date < today:
            advertisement.status = "expired"
            changed = True
    if changed:
        db.session.flush()


def active_advertisement(item_id: int, today: date | None = None) -> Advertisement | None:
    today = today or date.today()
    return (
        Advertisement.query.filter(
            Advertisement.item_id == item_id,
            Advertisement.status == "active",
            Advertisement.start_date <= today,
            Advertisement.end_date >= today,
        )
        .order_by(Advertisement.end_date.desc())
        .first()
    )


def promotion_weight_map(item_ids: list[int], today: date | None = None) -> dict[int, int]:
    """Mapping of item id → promotion ranking weight (0 when not promoted)."""
    if not item_ids:
        return {}
    today = today or date.today()
    ads = (
        Advertisement.query.join(PromotionLevel, PromotionLevel.name == Advertisement.promotion_level)
        .filter(
            Advertisement.item_id.in_(item_ids),
            Advertisement.status == "active",
            Advertisement.start_date <= today,
            Advertisement.end_date >= today,
            PromotionLevel.active.is_(True),
        )
        .all()
    )
    weights: dict[int, int] = {}
    for ad in ads:
        level = get_promotion_level(ad.promotion_level)
        weight = level.ranking_weight if level else 0
        if weight > weights.get(ad.item_id, 0):
            weights[ad.item_id] = weight
    for item_id in item_ids:
        weights.setdefault(item_id, 0)
    return weights


def promotion_weight(item_id: int, today: date | None = None) -> int:
    return promotion_weight_map([item_id], today).get(item_id, 0)


def active_promoted_item_ids(today: date | None = None) -> list[int]:
    """Ids of items with a currently running promotion.

    Used by marketplace search so promoted items stay visible in the result
    set while relevance still decides their rank.
    """
    today = today or date.today()
    rows = (
        db.session.query(Advertisement.item_id)
        .filter(
            Advertisement.status == "active",
            Advertisement.start_date <= today,
            Advertisement.end_date >= today,
        )
        .distinct()
        .all()
    )
    return [row[0] for row in rows]


def has_active_promotion(item_id: int) -> bool:
    return promotion_weight(item_id) > 0
