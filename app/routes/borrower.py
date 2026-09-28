"""Borrower area: dashboard, requests, active rentals and history."""

from datetime import date

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.extensions import db
from app.models import RentalRequest
from app.services import chat as chat_service
from app.services import rental as rental_service

blueprint = Blueprint("borrower", __name__)

HISTORY_STATUSES = ("completed", "cancelled", "rejected")
ACTIVE_RENTAL_STATUSES = ("approved", "active")


def _base_query():
    return RentalRequest.query.filter(RentalRequest.borrower_id == current_user.id)


def _rows(requests):
    return [(req, req.transaction) for req in requests]


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


@blueprint.route("/dashboard")
@login_required
def dashboard():
    rental_service.sync_rental_statuses()
    db.session.commit()

    requests = _base_query().order_by(RentalRequest.created_at.desc()).all()

    active = [r for r in requests if r.status in ACTIVE_RENTAL_STATUSES]
    pending = [r for r in requests if r.status == "pending"]
    approved = [r for r in requests if r.status == "approved"]
    active_only = [r for r in requests if r.status == "active"]
    completed = [r for r in requests if r.status == "completed"]
    cancelled = [r for r in requests if r.status == "cancelled"]
    rejected = [r for r in requests if r.status == "rejected"]

    total_spent = rental_service._sum(
        [r.transaction for r in requests if r.transaction and r.status in ("active", "completed", "approved")],
        "borrower_total",
    )

    return render_template(
        "borrower/dashboard.html",
        requests=requests,
        rows=_rows(requests),
        active_rows=_rows(active),
        pending_rows=_rows(pending),
        completed_rows=_rows(completed),
        total_spent=total_spent,
        counts={
            "active": len(active_only),
            "pending": len(pending),
            "approved": len(approved),
            "upcoming": len([r for r in active if r.end_date >= date.today()]),
            "completed": len(completed),
            "cancelled": len(cancelled),
            "rejected": len(rejected),
        },
        upcoming_returns=sorted(active, key=lambda r: r.end_date)[:5],
        unread_map=_unread_map(requests),
        chat_service=chat_service,
    )


@blueprint.route("/requests")
@login_required
def requests_list():
    rental_service.sync_rental_statuses()
    db.session.commit()

    requests = _base_query().order_by(RentalRequest.created_at.desc()).all()
    groups = {
        "pending": [r for r in requests if r.status == "pending"],
        "approved": [r for r in requests if r.status == "approved"],
        "rejected": [r for r in requests if r.status == "rejected"],
        "cancelled": [r for r in requests if r.status == "cancelled"],
    }
    return render_template(
        "borrower/requests.html",
        groups=groups,
        rows={key: _rows(value) for key, value in groups.items()},
        unread_map=_unread_map(requests),
    )


@blueprint.route("/rentals")
@login_required
def rentals():
    rental_service.sync_rental_statuses()
    db.session.commit()

    requests = (
        _base_query()
        .filter(RentalRequest.status.in_(ACTIVE_RENTAL_STATUSES + ("pending",)))
        .order_by(RentalRequest.start_date.asc())
        .all()
    )
    return render_template(
        "borrower/rentals.html",
        rows=_rows(requests),
        unread_map=_unread_map(requests),
    )


@blueprint.route("/history")
@login_required
def history():
    rental_service.sync_rental_statuses()
    db.session.commit()

    requests = (
        _base_query()
        .filter(RentalRequest.status.in_(HISTORY_STATUSES + ("completed",)))
        .order_by(RentalRequest.updated_at.desc())
        .all()
    )
    total_spent = rental_service._sum(
        [r.transaction for r in requests if r.transaction and r.status == "completed"],
        "borrower_total",
    )
    total_fees = rental_service._sum(
        [r.transaction for r in requests if r.transaction and r.status == "completed"],
        "borrower_service_fee",
    )
    return render_template(
        "borrower/history.html",
        rows=_rows(requests),
        total_spent=total_spent,
        total_fees=total_fees,
    )
