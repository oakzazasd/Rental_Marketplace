"""Lender area: item management, incoming requests, rentals and earnings."""

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app import constants as C
from app.extensions import db
from app.models import Advertisement, Item, ItemImage, RentalRequest, Transaction
from app.services import advertising as ad_service
from app.services import chat as chat_service
from app.services import image as image_service
from app.services import rental as rental_service

blueprint = Blueprint("lender", __name__)


def get_owned_item(item_id: int) -> Item:
    item = db.session.get(Item, item_id)
    if item is None or item.status == "deleted":
        abort(404)
    if item.owner_id != current_user.id:
        abort(403)
    return item


def _parse_money(raw, field_name: str) -> Decimal:
    raw = (raw or "").strip().replace(",", "")
    if raw == "":
        raise ValueError(f"{field_name} is required.")
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} must be a number.")
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    if value > Decimal("1000000"):
        raise ValueError(f"{field_name} is too large.")
    return value.quantize(Decimal("0.01"))


def validate_item_form(form) -> dict | None:
    """Return cleaned data or an error message."""
    name = (form.get("name") or "").strip()
    description = (form.get("description") or "").strip()
    category = (form.get("category") or "").strip()
    location = (form.get("location") or "").strip()
    status = (form.get("status") or "available").strip()

    if not name:
        return {"error": "Item name is required."}
    if len(name) > 150:
        return {"error": "Item name is too long (max 150 characters)."}
    if category not in C.CATEGORIES:
        return {"error": "Please choose a valid category."}
    if not location:
        return {"error": "Location is required."}
    if len(description) > 5000:
        return {"error": "Description is too long (max 5000 characters)."}
    if status not in ("available", "unavailable"):
        status = "available"

    try:
        price = _parse_money(form.get("price_per_day"), "Price per day")
        deposit = _parse_money(form.get("deposit"), "Deposit")
    except ValueError as exc:
        return {"error": str(exc)}

    if price <= 0:
        return {"error": "Price per day must be greater than 0."}

    return {
        "name": name,
        "description": description,
        "category": category,
        "location": location,
        "status": status,
        "price_per_day": price,
        "deposit": deposit,
    }


def _unread_map(requests) -> dict[int, int]:
    counts = {}
    for req in requests:
        room = chat_service.get_room_for_request(req.id)
        if room is None:
            continue
        count = chat_service.unread_count_for_room(room, current_user)
        if count:
            counts[req.id] = count
    return counts


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@blueprint.route("/dashboard")
@login_required
def dashboard():
    rental_service.sync_rental_statuses()
    ad_service.sync_advertisements()
    db.session.commit()

    my_items = Item.query.filter(Item.owner_id == current_user.id, Item.status != "deleted").all()
    incoming = (
        RentalRequest.query.join(Item, Item.id == RentalRequest.item_id)
        .filter(Item.owner_id == current_user.id)
        .order_by(RentalRequest.created_at.desc())
        .all()
    )

    transactions = rental_service.lender_transactions(
        current_user.id, ("approved", "active", "completed")
    )
    gross = rental_service._sum(transactions, "rental_subtotal")
    fees = rental_service._sum(transactions, "lender_platform_fee")
    net = rental_service._sum(transactions, "lender_payout")

    active_ads = Advertisement.query.filter(
        Advertisement.owner_id == current_user.id, Advertisement.status == "active"
    ).count()

    return render_template(
        "lender/dashboard.html",
        my_items=my_items,
        available_items=[i for i in my_items if i.status == "available"],
        unavailable_items=[i for i in my_items if i.status != "available"],
        incoming=incoming,
        rows=[(req, req.transaction) for req in incoming],
        pending=[r for r in incoming if r.status == "pending"],
        approved=[r for r in incoming if r.status == "approved"],
        active=[r for r in incoming if r.status == "active"],
        completed=[r for r in incoming if r.status == "completed"],
        gross_revenue=gross,
        platform_fees=fees,
        net_earnings=net,
        active_ads=active_ads,
        unread_map=_unread_map(incoming),
        recent=[r for r in incoming if r.status == "pending"][:5],
    )


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------
@blueprint.route("/items")
@login_required
def items():
    rental_service.sync_rental_statuses()
    db.session.commit()
    my_items = (
        Item.query.filter(Item.owner_id == current_user.id, Item.status != "deleted")
        .order_by(Item.created_at.desc())
        .all()
    )
    rental_counts = {}
    for item in my_items:
        rental_counts[item.id] = item.rental_requests.filter(
            RentalRequest.status.in_(("approved", "active", "completed"))
        ).count()
    return render_template("lender/items.html", items=my_items, rental_counts=rental_counts)


@blueprint.route("/items/create", methods=["GET", "POST"])
@login_required
def item_create():
    if request.method == "GET":
        return render_template("lender/item_form.html", item=None, categories=C.CATEGORIES)

    data = validate_item_form(request.form)
    if "error" in data:
        flash(data["error"], "danger")
        return render_template(
            "lender/item_form.html", item=None, categories=C.CATEGORIES, form_data=request.form.to_dict()
        ), 400

    item = Item(owner_id=current_user.id, **data)
    db.session.add(item)
    db.session.flush()

    files = request.files.getlist("images")
    saved = 0
    errors = []
    for file in files:
        if not file or not file.filename:
            continue
        try:
            relative_path = image_service.process_image(file)
        except image_service.ImageValidationError as exc:
            errors.append(str(exc))
            continue
        db.session.add(ItemImage(item_id=item.id, image_path=relative_path))
        saved += 1

    if not data["description"]:
        errors.append("Tip: add a description so borrowers know what they are renting.")

    db.session.commit()

    if errors:
        for message in errors:
            flash(message, "warning")
    flash(f"Item '{item.name}' created ({saved} image(s) uploaded).", "success")
    return redirect(url_for("lender.items"))


@blueprint.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def item_edit(item_id):
    item = get_owned_item(item_id)

    if request.method == "GET":
        return render_template(
            "lender/item_form.html", item=item, categories=C.CATEGORIES
        )

    data = validate_item_form(request.form)
    if "error" in data:
        flash(data["error"], "danger")
        return (
            render_template("lender/item_form.html", item=item, categories=C.CATEGORIES, form_data=request.form.to_dict()),
            400,
        )

    for key, value in data.items():
        setattr(item, key, value)
    db.session.commit()
    flash(f"Item '{item.name}' updated.", "success")
    return redirect(url_for("lender.items"))


@blueprint.route("/items/<int:item_id>/delete", methods=["POST"])
@login_required
def item_delete(item_id):
    item = get_owned_item(item_id)
    item.status = "deleted"
    db.session.commit()
    flash(f"'{item.name}' has been removed from the marketplace.", "info")
    return redirect(url_for("lender.items"))


@blueprint.route("/items/<int:item_id>/toggle", methods=["POST"])
@login_required
def item_toggle(item_id):
    item = get_owned_item(item_id)
    if item.status == "available":
        item.status = "unavailable"
        flash(f"'{item.name}' is now marked unavailable.", "info")
    else:
        item.status = "available"
        flash(f"'{item.name}' is now available for rent.", "success")
    db.session.commit()
    return redirect(url_for("lender.items"))


@blueprint.route("/items/<int:item_id>/images", methods=["POST"])
@login_required
def item_upload_image(item_id):
    item = get_owned_item(item_id)
    file = request.files.get("image")
    if file is None or not file.filename:
        flash("Choose an image to upload.", "warning")
        return redirect(url_for("lender.item_edit", item_id=item.id))
    try:
        relative_path = image_service.process_image(file)
    except image_service.ImageValidationError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("lender.item_edit", item_id=item.id))

    db.session.add(ItemImage(item_id=item.id, image_path=relative_path))
    db.session.commit()
    flash("Image uploaded.", "success")
    return redirect(url_for("lender.item_edit", item_id=item.id))


@blueprint.route("/images/<int:image_id>/delete", methods=["POST"])
@login_required
def image_delete(image_id):
    image = db.session.get(ItemImage, image_id)
    if image is None:
        abort(404)
    if image.item.owner_id != current_user.id:
        abort(403)
    item_id = image.item_id
    image_service.delete_stored_image(image.image_path)
    db.session.delete(image)
    db.session.commit()
    flash("Image removed.", "info")
    return redirect(url_for("lender.item_edit", item_id=item_id))


# ---------------------------------------------------------------------------
# Requests / rentals / earnings
# ---------------------------------------------------------------------------
@blueprint.route("/requests")
@login_required
def requests_list():
    rental_service.sync_rental_statuses()
    db.session.commit()

    incoming = (
        RentalRequest.query.join(Item, Item.id == RentalRequest.item_id)
        .filter(Item.owner_id == current_user.id)
        .order_by(RentalRequest.created_at.desc())
        .all()
    )
    groups = {
        "pending": [r for r in incoming if r.status == "pending"],
        "approved": [r for r in incoming if r.status == "approved"],
        "rejected": [r for r in incoming if r.status == "rejected"],
        "cancelled": [r for r in incoming if r.status == "cancelled"],
    }
    return render_template(
        "lender/requests.html",
        groups=groups,
        rows={key: _rows(value) for key, value in groups.items()},
        unread_map=_unread_map(incoming),
    )


def _rows(requests):
    return [(req, req.transaction) for req in requests]


@blueprint.route("/rentals")
@login_required
def rentals():
    rental_service.sync_rental_statuses()
    db.session.commit()

    incoming = (
        RentalRequest.query.join(Item, Item.id == RentalRequest.item_id)
        .filter(
            Item.owner_id == current_user.id,
            RentalRequest.status.in_(("approved", "active", "completed")),
        )
        .order_by(RentalRequest.start_date.asc())
        .all()
    )
    return render_template(
        "lender/rentals.html",
        rows=_rows(incoming),
        unread_map=_unread_map(incoming),
    )


@blueprint.route("/earnings")
@login_required
def earnings():
    rental_service.sync_rental_statuses()
    db.session.commit()

    completed = rental_service.lender_transactions(current_user.id, ("completed",))
    active = rental_service.lender_transactions(current_user.id, ("approved", "active"))
    pending = rental_service.lender_transactions(current_user.id, ("pending",))

    gross = rental_service._sum(completed, "rental_subtotal")
    fees = rental_service._sum(completed, "lender_platform_fee")
    net = rental_service._sum(completed, "lender_payout")

    pending_gross = rental_service._sum(pending, "rental_subtotal")
    pending_fees = rental_service._sum(pending, "lender_platform_fee")
    pending_net = rental_service._sum(pending, "lender_payout")

    active_gross = rental_service._sum(active, "rental_subtotal")
    active_fees = rental_service._sum(active, "lender_platform_fee")
    active_net = rental_service._sum(active, "lender_payout")

    return render_template(
        "lender/earnings.html",
        completed=completed,
        active=active,
        pending=pending,
        totals={
            "gross": gross,
            "fees": fees,
            "net": net,
            "pending_gross": pending_gross,
            "pending_fees": pending_fees,
            "pending_net": pending_net,
            "active_gross": active_gross,
            "active_fees": active_fees,
            "active_net": active_net,
        },
    )
