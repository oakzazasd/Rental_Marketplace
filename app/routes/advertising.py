"""Advertising / promoted listings routes."""

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import constants as C
from app.extensions import db
from app.models import Advertisement, Item, PromotionLevel
from app.services import advertising as ad_service

blueprint = Blueprint("advertising", __name__)


def get_owned_advertisement(ad_id: int) -> Advertisement:
    advertisement = db.session.get(Advertisement, ad_id)
    if advertisement is None:
        abort(404)
    if advertisement.owner_id != current_user.id:
        abort(403)
    return advertisement


@blueprint.route("/", strict_slashes=False)
@login_required
def index():
    ad_service.sync_advertisements()
    db.session.commit()

    mine = (
        Advertisement.query.filter(Advertisement.owner_id == current_user.id)
        .order_by(Advertisement.created_at.desc())
        .all()
    )
    groups = {
        "active": [a for a in mine if a.status == "active"],
        "expired": [a for a in mine if a.status == "expired"],
        "cancelled": [a for a in mine if a.status == "cancelled"],
        "pending": [a for a in mine if a.status == "pending"],
    }
    items = Item.query.filter(Item.owner_id == current_user.id, Item.status != "deleted").all()
    levels = PromotionLevel.query.filter(PromotionLevel.active.is_(True)).all()

    return render_template(
        "advertising/dashboard.html",
        groups=groups,
        items=items,
        levels=levels,
        duration_choices=C.AD_DURATION_CHOICES,
    )


@blueprint.route("/promote")
@login_required
def promote_select():
    items = Item.query.filter(Item.owner_id == current_user.id, Item.status != "deleted").all()
    if not items:
        flash("Create an item listing first, then promote it here.", "warning")
        return redirect(url_for("lender.item_create"))
    return render_template(
        "advertising/select_item.html",
        items=items,
    )


@blueprint.route("/promote/<int:item_id>", methods=["GET", "POST"])
@login_required
def promote_item(item_id):
    item = db.session.get(Item, item_id)
    if item is None or item.status == "deleted":
        abort(404)
    if item.owner_id != current_user.id:
        abort(403)

    levels = PromotionLevel.query.filter(PromotionLevel.active.is_(True)).all()
    level_names = [level.name for level in levels]

    if request.method == "POST":
        level = request.form.get("promotion_level") or ""
        try:
            duration = int(request.form.get("duration_days") or 0)
        except ValueError:
            duration = 0

        try:
            advertisement = ad_service.create_advertisement(
                item, current_user.id, level, duration
            )
            db.session.commit()
        except (ad_service.AdvertisingError, ValueError, TypeError) as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return (
                render_template(
                    "advertising/promote.html",
                    item=item,
                    levels=levels,
                    duration_choices=C.AD_DURATION_CHOICES,
                    quote=None,
                ),
                400,
            )

        flash(
            f"Promotion purchased: {advertisement.promotion_level} on '{item.name}' "
            f"for {advertisement.total_price} THB "
            f"({advertisement.start_date:%d %b %Y} – {advertisement.end_date:%d %b %Y}).",
            "success",
        )
        return redirect(url_for("advertising.index"))

    return render_template(
        "advertising/promote.html",
        item=item,
        levels=levels,
        duration_choices=C.AD_DURATION_CHOICES,
        quote=None,
    )


@blueprint.route("/quote", methods=["POST"])
@login_required
def quote():
    payload = request.get_json(silent=True) or {}
    category = payload.get("category") or ""
    level = payload.get("promotion_level") or ""
    try:
        duration = int(payload.get("duration_days") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid duration."}), 400

    if not level:
        return jsonify({"error": "Choose a promotion level."}), 400

    try:
        price = ad_service.calculate_ad_price(category, level, duration)
    except ad_service.AdvertisingError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(
        {
            "category": price["category"],
            "category_listing_count": price["category_listing_count"],
            "competition_level": price["competition_level"],
            "competition_multiplier": str(price["competition_multiplier"]),
            "promotion_level": price["promotion_level"],
            "promotion_level_multiplier": str(price["promotion_level_multiplier"]),
            "promotion_level_weight": price["promotion_level_weight"],
            "base_price": f"{price['base_price']:.2f}",
            "daily_price": f"{price['daily_price']:.2f}",
            "duration_days": price["duration_days"],
            "total_price": f"{price['total_price']:.2f}",
            "currency": price["currency"],
            "formatted": {
                "base_price": f"฿{price['base_price']:,.2f}",
                "daily_price": f"฿{price['daily_price']:,.2f}",
                "total_price": f"฿{price['total_price']:,.2f}",
            },
        }
    )


@blueprint.route("/<int:ad_id>/cancel", methods=["POST"])
@login_required
def cancel(ad_id):
    advertisement = get_owned_advertisement(ad_id)
    item_name = advertisement.item.name
    try:
        ad_service.cancel_advertisement(advertisement, current_user.id)
        db.session.commit()
    except ad_service.AdvertisingError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("advertising.index"))

    flash(f"Promotion for '{item_name}' cancelled.", "info")
    return redirect(url_for("advertising.index"))
