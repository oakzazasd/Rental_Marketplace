"""Rental workflow: availability, requests, status transitions.

All availability checks and status transitions live here so routes stay thin
and the overlap rules are enforced on the backend in exactly one place.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from app import constants as C
from app.extensions import db
from app.models import Item, RentalRequest, Transaction, User
from app.services import chat as chat_service
from app.services.pricing import calculate_rental_price


class RentalError(Exception):
    """User facing rental error."""


def number_of_days(start: date, end: date) -> int:
    """Rental length in days, counting both the start and the end day."""
    return (end - start).days + 1


def find_conflict(
    item_id: int, start: date, end: date, exclude_request_id: int | None = None
) -> RentalRequest | None:
    query = RentalRequest.query.filter(
        RentalRequest.item_id == item_id,
        RentalRequest.status.in_(C.RENTAL_BLOCKING_STATUSES),
        RentalRequest.start_date <= end,
        RentalRequest.end_date >= start,
    )
    if exclude_request_id:
        query = query.filter(RentalRequest.id != exclude_request_id)
    return query.order_by(RentalRequest.start_date.asc()).first()


def is_item_available(
    item_id: int, start: date, end: date, exclude_request_id: int | None = None
) -> tuple[bool, RentalRequest | None]:
    conflict = find_conflict(item_id, start, end, exclude_request_id)
    return conflict is None, conflict


def validate_dates(start: date, end: date, max_days: int = 90) -> int:
    today = date.today()
    if start is None or end is None:
        raise RentalError("Please select both a start date and an end date.")
    if end < start:
        raise RentalError("The end date must be on or after the start date.")
    if start < today:
        raise RentalError("The start date cannot be in the past.")
    days = number_of_days(start, end)
    if days < 1:
        raise RentalError("Rental must be at least one day.")
    if days > max_days:
        raise RentalError(f"Rental cannot be longer than {max_days} days.")
    return days


def create_rental_request(item: Item, borrower: User, start: date, end: date) -> RentalRequest:
    if item.status != "available":
        raise RentalError("This item is not available for rent right now.")
    if item.owner_id == borrower.id:
        raise RentalError("You cannot request your own item.")

    days = validate_dates(start, end)

    available, conflict = is_item_available(item.id, start, end)
    if not available:
        raise RentalError(
            f"Item is already booked between {conflict.start_date:%d %b %Y} and "
            f"{conflict.end_date:%d %b %Y}."
        )

    breakdown = calculate_rental_price(
        daily_price=item.price_per_day,
        rental_days=days,
        deposit=item.deposit,
    )

    request = RentalRequest(
        item_id=item.id,
        borrower_id=borrower.id,
        start_date=start,
        end_date=end,
        number_of_days=days,
        status="pending",
    )
    db.session.add(request)
    db.session.flush()

    transaction = Transaction(
        rental_request_id=request.id,
        base_amount=breakdown.base_amount,
        discount_rate=breakdown.discount_rate,
        discount_amount=breakdown.discount_amount,
        rental_subtotal=breakdown.rental_subtotal,
        borrower_service_fee_rate=breakdown.borrower_fee_rate,
        borrower_service_fee=breakdown.borrower_service_fee,
        lender_platform_fee_rate=breakdown.lender_fee_rate,
        lender_platform_fee=breakdown.lender_platform_fee,
        borrower_total=breakdown.borrower_total,
        lender_payout=breakdown.lender_payout,
        platform_revenue=breakdown.platform_revenue,
        deposit=breakdown.deposit,
        currency=breakdown.currency,
        status="pending",
    )
    db.session.add(transaction)
    request.transaction = transaction

    chat_service.ensure_chat(request)
    db.session.flush()
    return request


def _require_status(request: RentalRequest, allowed: tuple[str, ...]) -> None:
    if request.status not in allowed:
        labels = ", ".join(C.RENTAL_STATUS_LABELS[s] for s in allowed)
        raise RentalError(
            f"This request is '{C.RENTAL_STATUS_LABELS.get(request.status, request.status)}' "
            f"and can no longer be changed (expected: {labels})."
        )


def approve_request(request: RentalRequest, lender: User) -> RentalRequest:
    if request.item.owner_id != lender.id:
        raise RentalError("Only the item owner can approve this request.")
    _require_status(request, ("pending",))

    available, conflict = is_item_available(
        request.item_id, request.start_date, request.end_date, exclude_request_id=request.id
    )
    if not available:
        raise RentalError(
            f"The requested dates now overlap another rental "
            f"({conflict.start_date:%d %b %Y} – {conflict.end_date:%d %b %Y})."
        )

    request.status = "approved"
    if request.transaction:
        request.transaction.status = "authorized"
    chat_service.ensure_chat(request)
    db.session.flush()
    return request


def reject_request(request: RentalRequest, lender: User) -> RentalRequest:
    if request.item.owner_id != lender.id:
        raise RentalError("Only the item owner can reject this request.")
    _require_status(request, ("pending",))
    request.status = "rejected"
    if request.transaction:
        request.transaction.status = "refunded"
    chat_service.close_and_delete_chat(request)
    db.session.flush()
    return request


def cancel_request(request: RentalRequest, borrower: User) -> RentalRequest:
    if request.borrower_id != borrower.id:
        raise RentalError("Only the borrower can cancel this request.")
    _require_status(request, ("pending",))
    request.status = "cancelled"
    if request.transaction:
        request.transaction.status = "refunded"
    chat_service.close_and_delete_chat(request)
    db.session.flush()
    return request


def complete_rental(request: RentalRequest) -> RentalRequest:
    """Finalise a rental: mark completed, settle the transaction, delete chat."""
    _require_status(request, ("approved", "active"))
    request.status = "completed"
    if request.transaction:
        request.transaction.status = "completed"
    chat_service.close_and_delete_chat(request)
    db.session.flush()
    return request


def activate_request(request: RentalRequest) -> None:
    if request.status == "approved" and request.start_date <= date.today():
        request.status = "active"
        db.session.flush()


def sync_rental_statuses() -> None:
    """Bring statuses up to date with today's date.

    * approved requests whose start date has arrived become Active
    * active rentals whose end date has passed are completed (which also
      finalises the transaction and deletes the temporary chat)
    """
    today = date.today()

    approved = RentalRequest.query.filter(RentalRequest.status == "approved").all()
    for request in approved:
        if request.start_date <= today:
            request.status = "active"

    active = RentalRequest.query.filter(RentalRequest.status == "active").all()
    for request in active:
        if request.end_date < today:
            request.status = "completed"
            if request.transaction:
                request.transaction.status = "completed"
            chat_service.close_and_delete_chat(request)

    if approved or active:
        db.session.flush()


def can_complete_manually(request: RentalRequest, user) -> bool:
    if request.status not in ("approved", "active"):
        return False
    if user is None or not user.is_authenticated:
        return False
    # The lender (item owner) may close the rental once the item is returned.
    # The borrower may also confirm the return.
    return user.id in {request.item.owner_id, request.borrower_id}


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------
def _sum(rows, attr) -> Decimal:
    total = Decimal("0.00")
    for row in rows:
        value = getattr(row, attr)
        if value is not None:
            total += Decimal(value)
    return total.quantize(Decimal("0.01"))


def borrower_transactions(borrower_id: int, statuses: tuple[str, ...]) -> list[Transaction]:
    return (
        Transaction.query.join(RentalRequest)
        .filter(RentalRequest.borrower_id == borrower_id, RentalRequest.status.in_(statuses))
        .order_by(RentalRequest.created_at.desc())
        .all()
    )


def lender_transactions(owner_id: int, statuses: tuple[str, ...]) -> list[Transaction]:
    return (
        Transaction.query.join(RentalRequest)
        .join(Item, Item.id == RentalRequest.item_id)
        .filter(Item.owner_id == owner_id, RentalRequest.status.in_(statuses))
        .order_by(RentalRequest.created_at.desc())
        .all()
    )
