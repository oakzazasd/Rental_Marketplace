"""Rental request lifecycle routes (create / approve / reject / cancel / complete)."""

from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Item, RentalRequest
from app.services import chat as chat_service
from app.services import rental as rental_service

blueprint = Blueprint("rentals", __name__)


def _parse_date(raw):
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def get_participant_request(request_id: int) -> RentalRequest:
    rental_request = db.session.get(RentalRequest, request_id)
    if rental_request is None:
        abort(404)
    user_id = current_user.id
    participants = {rental_request.borrower_id, rental_request.item.owner_id}
    if user_id not in participants:
        abort(403)
    return rental_request


@blueprint.route("/rentals/request/<int:item_id>", methods=["POST"])
@login_required
def create_request(item_id):
    item = db.session.get(Item, item_id)
    if item is None or item.status == "deleted":
        abort(404)

    start = _parse_date(request.form.get("start_date"))
    end = _parse_date(request.form.get("end_date"))

    try:
        rental_request = rental_service.create_rental_request(item, current_user, start, end)
        db.session.commit()
    except rental_service.RentalError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("marketplace.item_detail", item_id=item.id))
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("marketplace.item_detail", item_id=item.id))

    flash(
        f"Request sent to {item.owner.name} for {item.name} "
        f"({rental_request.number_of_days} day(s)). You can now chat with the lender.",
        "success",
    )
    return redirect(url_for("rentals.detail", request_id=rental_request.id))


@blueprint.route("/rentals/<int:request_id>")
@login_required
def detail(request_id):
    rental_service.sync_rental_statuses()
    db.session.commit()

    rental_request = get_participant_request(request_id)
    item = rental_request.item
    transaction = rental_request.transaction
    is_lender = current_user.id == item.owner_id
    room = chat_service.get_room_for_request(rental_request.id)
    chat_available = (
        room is not None and chat_service.user_can_access(room, current_user)
    )
    return render_template(
        "rentals/detail.html",
        rental_request=rental_request,
        item=item,
        transaction=transaction,
        is_lender=is_lender,
        borrower=rental_request.borrower,
        lender=item.owner,
        chat_available=chat_available,
        can_cancel=rental_request.status == "pending"
        and current_user.id == rental_request.borrower_id,
        can_decide=rental_request.status == "pending"
        and current_user.id == item.owner_id,
        can_complete=rental_service.can_complete_manually(rental_request, current_user),
    )


@blueprint.route("/rentals/<int:request_id>/approve", methods=["POST"])
@login_required
def approve(request_id):
    rental_request = get_participant_request(request_id)
    try:
        rental_service.approve_request(rental_request, current_user)
        db.session.commit()
    except rental_service.RentalError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("rentals.detail", request_id=request_id))

    flash(
        f"Request approved. Rental of {rental_request.item.name} is now active/confirmed.",
        "success",
    )
    return redirect(url_for("rentals.detail", request_id=request_id))


@blueprint.route("/rentals/<int:request_id>/reject", methods=["POST"])
@login_required
def reject(request_id):
    rental_request = get_participant_request(request_id)
    try:
        rental_service.reject_request(rental_request, current_user)
        db.session.commit()
    except rental_service.RentalError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("rentals.detail", request_id=request_id))

    flash("Request rejected. The chat has been closed and deleted.", "info")
    return redirect(url_for("lender.requests_list"))


@blueprint.route("/rentals/<int:request_id>/cancel", methods=["POST"])
@login_required
def cancel(request_id):
    rental_request = get_participant_request(request_id)
    try:
        rental_service.cancel_request(rental_request, current_user)
        db.session.commit()
    except rental_service.RentalError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("rentals.detail", request_id=request_id))

    flash("Request cancelled. The chat has been closed and deleted.", "info")
    return redirect(url_for("borrower.requests_list"))


@blueprint.route("/rentals/<int:request_id>/complete", methods=["POST"])
@login_required
def complete(request_id):
    rental_request = get_participant_request(request_id)
    if not rental_service.can_complete_manually(rental_request, current_user):
        flash("This rental cannot be completed yet.", "warning")
        return redirect(url_for("rentals.detail", request_id=request_id))

    try:
        rental_service.complete_rental(rental_request)
        db.session.commit()
    except rental_service.RentalError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("rentals.detail", request_id=request_id))

    flash(
        "Rental completed, transaction finalised and the temporary chat has been deleted.",
        "success",
    )
    return redirect(url_for("rentals.detail", request_id=request_id))
