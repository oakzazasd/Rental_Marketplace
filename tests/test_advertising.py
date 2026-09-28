"""Advertising: category competition pricing, levels, duration, lifecycle, ranking."""

from datetime import date, timedelta
from decimal import Decimal

from helpers import login, make_item, make_user

from app.extensions import db
from app.models import Advertisement, Item, PromotionLevel
from app.services.advertising import (
    AdvertisingError,
    active_listing_count,
    calculate_ad_price,
    create_advertisement,
    promotion_weight,
    sync_advertisements,
)


def _fill_category(owner, category, count):
    for index in range(count):
        db.session.add(
            Item(
                owner_id=owner.id,
                name=f"{category} item {index}",
                description="demo",
                category=category,
                price_per_day="50.00",
                deposit="0",
                location="KMITL",
                status="available",
            )
        )
    db.session.commit()


def test_competition_multiplier_low(app_ctx):
    owner = make_user()
    _fill_category(owner, "Projector", 5)
    assert active_listing_count("Projector") == 5
    price = calculate_ad_price("Projector", "Basic", 7)
    assert price["competition_multiplier"] == Decimal("1.0000")
    assert price["daily_price"] == Decimal("20.00")
    assert price["total_price"] == Decimal("140.00")


def test_competition_multiplier_medium(app_ctx):
    owner = make_user()
    _fill_category(owner, "Tools", 35)
    price = calculate_ad_price("Tools", "Basic", 1)
    assert price["competition_multiplier"] == Decimal("1.2500")
    assert price["daily_price"] == Decimal("25.00")


def test_competition_multiplier_high(app_ctx):
    owner = make_user()
    _fill_category(owner, "Calculator", 60)
    assert active_listing_count("Calculator") == 60
    price = calculate_ad_price("Calculator", "Basic", 7)
    assert price["competition_multiplier"] == Decimal("1.5000")
    assert price["daily_price"] == Decimal("30.00")
    assert price["total_price"] == Decimal("210.00")


def test_competition_multiplier_very_high(app_ctx):
    owner = make_user()
    _fill_category(owner, "Books", 150)
    price = calculate_ad_price("Books", "Basic", 1)
    assert price["competition_multiplier"] == Decimal("2.0000")
    assert price["daily_price"] == Decimal("40.00")


def test_premium_price_example_from_spec(app_ctx):
    owner = make_user()
    _fill_category(owner, "Calculator", 60)
    price = calculate_ad_price("Calculator", "Premium", 7)
    # ฿20 × 1.5 competition × 2.0 premium = ฿60/day × 7 = ฿420
    assert price["promotion_level_multiplier"] == Decimal("2.0000")
    assert price["daily_price"] == Decimal("60.00")
    assert price["total_price"] == Decimal("420.00")


def test_standard_level_multiplier(app_ctx):
    owner = make_user()
    _fill_category(owner, "Camera", 10)
    price = calculate_ad_price("Camera", "Standard", 3)
    assert price["promotion_level_multiplier"] == Decimal("1.5000")
    assert price["daily_price"] == Decimal("30.00")
    assert price["total_price"] == Decimal("90.00")


def test_duration_choices(app_ctx):
    make_user()
    for days in (1, 3, 7, 14, 30):
        price = calculate_ad_price("Other", "Basic", days)
        assert price["duration_days"] == days
        assert price["total_price"] == Decimal(f"{20 * days}.00")


def test_invalid_duration_rejected(app_ctx):
    make_user()
    try:
        calculate_ad_price("Other", "Basic", 2)
        raised = False
    except AdvertisingError:
        raised = True
    assert raised


def test_unknown_level_rejected(app_ctx):
    make_user()
    try:
        calculate_ad_price("Other", "Diamond", 7)
        raised = False
    except AdvertisingError:
        raised = True
    assert raised


def test_create_and_cancel_advertisement(client, app_ctx):
    owner = make_user()
    item = make_item(owner, category="Calculator")
    login(client)

    response = client.post(
        f"/lender/advertising/promote/{item.id}",
        data={"promotion_level": "Premium", "duration_days": "7"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    ad = Advertisement.query.first()
    assert ad is not None
    assert ad.status == "active"
    assert ad.promotion_level == "Premium"
    assert ad.total_price == Decimal("280.00")  # ฿20 × 1.0 competition × 2.0 premium × 7 days
    assert ad.end_date == ad.start_date + timedelta(days=6)
    assert promotion_weight(item.id) == 50

    client.post(f"/lender/advertising/{ad.id}/cancel", follow_redirects=True)
    db.session.refresh(ad)
    assert ad.status == "cancelled"
    assert promotion_weight(item.id) == 0


def test_only_owner_can_promote(client, app_ctx):
    owner = make_user(email="owner@kmitl.ac.th", student_id="6507123456")
    item = make_item(owner)
    make_user(email="other@kmitl.ac.th", student_id="6507654321")
    login(client, email="other@kmitl.ac.th")

    assert client.get(f"/lender/advertising/promote/{item.id}").status_code == 403
    response = client.post(
        f"/lender/advertising/promote/{item.id}",
        data={"promotion_level": "Basic", "duration_days": "1"},
    )
    assert response.status_code == 403
    assert Advertisement.query.count() == 0


def test_expired_advertisement_has_no_weight(app_ctx):
    owner = make_user()
    item = make_item(owner)
    ad = create_advertisement(item, owner.id, "Premium", 3)
    db.session.commit()
    assert promotion_weight(item.id) == 50

    ad.end_date = date.today() - timedelta(days=1)
    db.session.commit()
    sync_advertisements()
    db.session.commit()

    db.session.refresh(ad)
    assert ad.status == "expired"
    assert promotion_weight(item.id) == 0


def test_quote_endpoint(client, app_ctx):
    owner = make_user()
    item = make_item(owner, category="Calculator")
    login(client)

    response = client.post(
        "/lender/advertising/quote",
        json={"category": "Calculator", "promotion_level": "Premium",
              "duration_days": 7},
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["competition_multiplier"] == "1.0000"
    assert payload["promotion_level_multiplier"] == "2.0000"
    assert payload["daily_price"] == "40.00"
    assert payload["total_price"] == "280.00"


def test_promoted_listing_is_labelled(client, app_ctx):
    owner = make_user()
    item = make_item(owner, name="Gaming Laptop", category="Computer")
    ad = create_advertisement(item, owner.id, "Standard", 7)
    db.session.commit()

    login(client)
    page = client.get("/items").data.decode()
    assert "Sponsored" in page
    assert "Gaming Laptop" in page


def test_promotion_levels_are_configurable(app_ctx):
    basic = PromotionLevel.query.filter_by(name="Basic").first()
    standard = PromotionLevel.query.filter_by(name="Standard").first()
    premium = PromotionLevel.query.filter_by(name="Premium").first()
    assert basic.ranking_weight == 10 and basic.price_multiplier == Decimal("1.0000")
    assert standard.ranking_weight == 25 and standard.price_multiplier == Decimal("1.5000")
    assert premium.ranking_weight == 50 and premium.price_multiplier == Decimal("2.0000")
