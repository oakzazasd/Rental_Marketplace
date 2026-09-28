"""Combined borrower + lender overview dashboard."""

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Advertisement, Item, RentalRequest, Transaction
from app.services import advertising as ad_service
from app.services import rental as rental_service

blueprint = Blueprint("dashboard", __name__)

BORROWER_COUNT_STATUSES = ("pending", "approved", "active", "completed", "cancelled", "rejected")
LENDER_COUNT_STATUSES = ("pending", "approved", "active", "completed", "cancelled", "rejected")


@blueprint.route("/dashboard")
@login_required
def index():
    rental_service.sync_rental_statuses()
    ad_service.sync_advertisements()
    db.session.commit()

    borrower_requests = (
        RentalRequest.query.filter(RentalRequest.borrower_id == current_user.id)
        .order_by(RentalRequest.created_at.desc())
        .all()
    )
    lender_requests = (
        RentalRequest.query.join(Item, Item.id == RentalRequest.item_id)
        .filter(Item.owner_id == current_user.id)
        .order_by(RentalRequest.created_at.desc())
        .all()
    )

    borrower_counts = {status: 0 for status in BORROWER_COUNT_STATUSES}
    for req in borrower_requests:
        borrower_counts[req.status] = borrower_counts.get(req.status, 0) + 1

    lender_counts = {status: 0 for status in LENDER_COUNT_STATUSES}
    for req in lender_requests:
        lender_counts[req.status] = lender_counts.get(req.status, 0) + 1

    my_items = Item.query.filter(Item.owner_id == current_user.id, Item.status != "deleted").all()
    available_items = [i for i in my_items if i.status == "available"]

    spent = rental_service._sum(
        [r.transaction for r in borrower_requests if r.transaction and r.status in ("active", "completed", "approved")],
        "borrower_total",
    )
    earnings = rental_service.lender_transactions(
        current_user.id, ("active", "completed", "approved")
    )
    gross = rental_service._sum(earnings, "rental_subtotal")
    fees = rental_service._sum(earnings, "lender_platform_fee")
    net = rental_service._sum(earnings, "lender_payout")

    active_ads = Advertisement.query.filter(
        Advertisement.owner_id == current_user.id,
        Advertisement.status == "active",
    ).count()

    recent = (borrower_requests + lender_requests)
    seen = set()
    deduped = []
    for req in sorted(recent, key=lambda r: r.created_at, reverse=True):
        if req.id in seen:
            continue
        seen.add(req.id)
        deduped.append(req)

    return render_template(
        "dashboard.html",
        borrower_requests=borrower_requests,
        lender_requests=lender_requests,
        borrower_counts=borrower_counts,
        lender_counts=lender_counts,
        my_items=my_items,
        available_items=available_items,
        unavailable_items=[i for i in my_items if i.status != "available"],
        total_spent=spent,
        gross_revenue=gross,
        platform_fees=fees,
        net_earnings=net,
        active_ads=active_ads,
        recent_requests=deduped[:6],
        upcoming_returns=sorted(
            [r for r in borrower_requests if r.status == "active"],
            key=lambda r: r.end_date,
        )[:5],
        pending_lender_requests=[
            r for r in lender_requests if r.status == "pending"
        ][:5],
    )
