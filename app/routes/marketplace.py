"""Marketplace browsing, server-side search, filters and item details."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import login_required

from app import constants as C
from app.extensions import db
from app.models import Item, RentalRequest, User
from app.services import advertising as ad_service
from app.services import rental as rental_service
from app.services.pricing import calculate_rental_price
from app.utils import format_thb

blueprint = Blueprint("marketplace", __name__)

PAGE_SIZE = 12
RELEVANCE_NAME = 40
RELEVANCE_CATEGORY = 30
RELEVANCE_DESCRIPTION = 15
RELEVANCE_LOCATION = 5
RELEVANCE_CAP = 100
AVAILABILITY_BONUS = 8

SORT_CHOICES = ("relevance", "newest", "price_asc", "price_desc")


def score_relevance(item: Item, terms: list[str]) -> int:
    """Relevance score capped at 100 so promotion never fully overrides it."""
    if not terms:
        return 0
    name = (item.name or "").lower()
    description = (item.description or "").lower()
    category = (item.category or "").lower()
    location = (item.location or "").lower()

    score = 0
    for term in terms:
        if term in name:
            score += RELEVANCE_NAME
        if term in category:
            score += RELEVANCE_CATEGORY
        if term in description:
            score += RELEVANCE_DESCRIPTION
        if term in location:
            score += RELEVANCE_LOCATION
    return min(score, RELEVANCE_CAP)


def final_score(item: Item, terms: list[str], promotion_weight: int) -> int:
    """final_score = relevance + promotion weight (+ availability bonus)."""
    score = score_relevance(item, terms) + promotion_weight
    if item.status == "available":
        score += AVAILABILITY_BONUS
    return score


def parse_search_args():
    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()
    if category and category not in C.CATEGORIES:
        category = ""
    availability = (request.args.get("availability") or "").strip()
    if availability not in ("", "available", "all"):
        availability = ""
    sort = (request.args.get("sort") or "").strip()
    if sort not in SORT_CHOICES:
        sort = "relevance" if q else "newest"

    def parse_price(raw):
        raw = (raw or "").strip()
        if not raw:
            return None
        try:
            value = Decimal(raw)
        except (InvalidOperation, ValueError):
            return None
        if value < 0:
            return None
        return value

    min_price = parse_price(request.args.get("min_price"))
    max_price = parse_price(request.args.get("max_price"))
    if min_price is not None and max_price is not None and min_price > max_price:
        min_price, max_price = max_price, min_price

    terms = [term for term in q.lower().split() if term]
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    return {
        "q": q,
        "terms": terms,
        "category": category,
        "availability": availability,
        "sort": sort,
        "min_price": min_price,
        "max_price": max_price,
        "page": page,
    }


def query_items(filters) -> list[Item]:
    query = Item.query.filter(Item.status != "deleted")

    if filters["category"]:
        query = query.filter(Item.category == filters["category"])
    if filters["availability"] == "available":
        query = query.filter(Item.status == "available")
    if filters["min_price"] is not None:
        query = query.filter(Item.price_per_day >= filters["min_price"])
    if filters["max_price"] is not None:
        query = query.filter(Item.price_per_day <= filters["max_price"])

    if filters["terms"]:
        term_query = query
        for term in filters["terms"]:
            pattern = f"%{term}%"
            term_query = term_query.filter(
                db.or_(
                    Item.name.ilike(pattern),
                    Item.description.ilike(pattern),
                    Item.category.ilike(pattern),
                    Item.location.ilike(pattern),
                )
            )
        matched = term_query.all()

        # Promoted listings stay in the result set even when they do not match
        # the query — their relevance score is 0, so a strongly relevant
        # listing is always ranked above them.
        promoted_ids = set(ad_service.active_promoted_item_ids())
        if promoted_ids:
            seen = {item.id for item in matched}
            extras = (
                query.filter(Item.id.in_(promoted_ids))
                .all()
            )
            items = matched + [item for item in extras if item.id not in seen]
        else:
            items = matched
    else:
        items = query.all()

    weights = ad_service.promotion_weight_map([item.id for item in items])

    if filters["sort"] == "price_asc":
        items.sort(key=lambda i: (i.price_per_day, i.id))
    elif filters["sort"] == "price_desc":
        items.sort(key=lambda i: (-i.price_per_day, -i.id))
    elif filters["sort"] == "newest":
        items.sort(key=lambda i: (i.created_at, i.id), reverse=True)
    else:
        items.sort(
            key=lambda i: (
                -final_score(i, filters["terms"], weights.get(i.id, 0)),
                -(i.created_at.timestamp() if i.created_at else 0),
            )
        )
    return items


def build_search_url(filters, page=None) -> str:
    from flask import url_for

    params = {}
    if filters["q"]:
        params["q"] = filters["q"]
    if filters["category"]:
        params["category"] = filters["category"]
    if filters["availability"]:
        params["availability"] = filters["availability"]
    if filters["sort"]:
        params["sort"] = filters["sort"]
    if filters["min_price"] is not None:
        params["min_price"] = str(filters["min_price"])
    if filters["max_price"] is not None:
        params["max_price"] = str(filters["max_price"])
    if page:
        params["page"] = page
    return url_for("marketplace.items", **params)


@blueprint.route("/")
def index():
    return items()


@blueprint.route("/items")
@login_required
def items():
    rental_service.sync_rental_statuses()
    ad_service.sync_advertisements()
    db.session.commit()

    filters = parse_search_args()
    items = query_items(filters)

    total = len(items)
    page = filters["page"]
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)
    start = (page - 1) * PAGE_SIZE
    page_items = items[start : start + PAGE_SIZE]

    promo_ids = [item.id for item in page_items]
    weights = ad_service.promotion_weight_map(promo_ids)

    return render_template(
        "marketplace/index.html",
        items=page_items,
        promotion_weights=weights,
        filters=filters,
        total=total,
        page=page,
        total_pages=total_pages,
        build_search_url=build_search_url,
        sort_choices=SORT_CHOICES,
    )


@blueprint.route("/items/<int:item_id>")
@login_required
def item_detail(item_id):
    item = db.session.get(Item, item_id)
    if item is None or item.status == "deleted":
        abort(404)

    rental_service.sync_rental_statuses()
    ad_service.sync_advertisements()
    db.session.commit()

    active_ad = ad_service.active_advertisement(item.id)
    promotion_weight = ad_service.promotion_weight(item.id)

    related = (
        Item.query.filter(
            Item.status != "deleted",
            Item.category == item.category,
            Item.id != item.id,
        )
        .order_by(Item.created_at.desc())
        .limit(8)
        .all()
    )
    related_weights = ad_service.promotion_weight_map([r.id for r in related])
    related = sorted(
        related, key=lambda i: -related_weights.get(i.id, 0)
    )[:4]

    upcoming = (
        RentalRequest.query.filter(
            RentalRequest.item_id == item.id,
            RentalRequest.status.in_(("pending", "approved", "active")),
        )
        .order_by(RentalRequest.start_date.asc())
        .all()
    )

    today = datetime.utcnow().date()
    quote = calculate_rental_price(item.price_per_day, 1, deposit=item.deposit)

    return render_template(
        "marketplace/detail.html",
        item=item,
        owner=item.owner,
        active_ad=active_ad,
        promotion_weight=promotion_weight,
        related=related,
        related_weights=related_weights,
        upcoming=upcoming,
        today=today,
        default_quote=quote,
        default_quote_formatted=_format_breakdown(quote),
    )


def _format_breakdown(breakdown) -> dict:
    return {
        "daily_price": format_thb(breakdown.daily_price),
        "rental_days": breakdown.rental_days,
        "base_amount": format_thb(breakdown.base_amount),
        "discount_rate": f"{(breakdown.discount_rate * 100):.0f}%",
        "discount_amount": format_thb(breakdown.discount_amount),
        "rental_subtotal": format_thb(breakdown.rental_subtotal),
        "borrower_fee_rate": f"{(breakdown.borrower_fee_rate * 100):.0f}%",
        "borrower_service_fee": format_thb(breakdown.borrower_service_fee),
        "borrower_total": format_thb(breakdown.borrower_total),
        "lender_fee_rate": f"{(breakdown.lender_fee_rate * 100):.0f}%",
        "lender_platform_fee": format_thb(breakdown.lender_platform_fee),
        "lender_payout": format_thb(breakdown.lender_payout),
        "deposit": format_thb(breakdown.deposit),
        "amount_required": format_thb(breakdown.amount_required),
        "currency": breakdown.currency,
    }


def _parse_date(raw):
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


@blueprint.route("/api/items/<int:item_id>/quote")
@login_required
def item_quote(item_id):
    """Server-side pricing + availability quote for the item date picker."""
    item = db.session.get(Item, item_id)
    if item is None or item.status == "deleted":
        return jsonify({"error": "Item not found."}), 404

    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    if start is None or end is None:
        return jsonify({"error": "Please select a start and an end date."}), 400

    try:
        days = rental_service.validate_dates(start, end)
    except rental_service.RentalError as exc:
        return jsonify({"error": str(exc)}), 400

    available, conflict = rental_service.is_item_available(item.id, start, end)
    breakdown = calculate_rental_price(item.price_per_day, days, deposit=item.deposit)

    payload = {
        "available": available and item.status == "available",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "breakdown": _format_breakdown(breakdown),
        "raw": {key: str(value) for key, value in breakdown.as_dict().items()},
    }
    if conflict is not None:
        payload["conflict"] = (
            f"Already booked {conflict.start_date:%d %b %Y} – {conflict.end_date:%d %b %Y}"
        )
    if item.status != "available":
        payload["available"] = False
        payload["conflict"] = "This item is currently marked unavailable."
    return jsonify(payload)
