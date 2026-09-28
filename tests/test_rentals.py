"""Rental requests: dates, overlap prevention, approval workflow, chat lifecycle."""

from datetime import date, timedelta

from helpers import login, make_item, make_request, make_user

from app.extensions import db
from app.models import ChatMessage, ChatRoom, RentalRequest, Transaction
from app.services import rental as rental_service


def _days_around(offset_start=1, length=7):
    start = date.today() + timedelta(days=offset_start)
    end = start + timedelta(days=length - 1)
    return start, end


def _login_pair(client, app_ctx):
    borrower = make_user(email="borrower@kmitl.ac.th", student_id="6507000010",
                         name="Borrower One")
    lender = make_user(email="lender@kmitl.ac.th", student_id="6507000020",
                       name="Lender One")
    item = make_item(lender)
    return borrower, lender, item


def test_create_rental_request(client, app_ctx):
    borrower, lender, item = _login_pair(client, app_ctx)
    login(client, email="borrower@kmitl.ac.th")
    start, end = _days_around()

    response = client.post(
        f"/rentals/request/{item.id}",
        data={"start_date": start.isoformat(), "end_date": end.isoformat()},
        follow_redirects=True,
    )
    assert response.status_code == 200
    request = RentalRequest.query.first()
    assert request is not None
    assert request.status == "pending"
    assert request.number_of_days == 7
    assert request.transaction is not None
    assert request.transaction.borrower_total == 661.50
    assert request.chat_room is not None


def test_invalid_dates_rejected(client, app_ctx):
    borrower, lender, item = _login_pair(client, app_ctx)
    login(client, email="borrower@kmitl.ac.th")

    end = date.today() + timedelta(days=5)
    start = end + timedelta(days=2)  # end before start
    client.post(
        f"/rentals/request/{item.id}",
        data={"start_date": start.isoformat(), "end_date": end.isoformat()},
        follow_redirects=True,
    )
    assert RentalRequest.query.count() == 0

    past = date.today() - timedelta(days=3)
    client.post(
        f"/rentals/request/{item.id}",
        data={"start_date": past.isoformat(),
              "end_date": (past + timedelta(days=2)).isoformat()},
        follow_redirects=True,
    )
    assert RentalRequest.query.count() == 0


def test_overlapping_rental_rejected(client, app_ctx):
    borrower, lender, item = _login_pair(client, app_ctx)
    start, end = _days_around()
    make_request(item, borrower, start, end)

    login(client, email="borrower@kmitl.ac.th")
    client.post(
        f"/rentals/request/{item.id}",
        data={
            "start_date": (start + timedelta(days=2)).isoformat(),
            "end_date": (end + timedelta(days=2)).isoformat(),
        },
        follow_redirects=True,
    )
    assert RentalRequest.query.count() == 1


def test_non_overlapping_dates_allowed(client, app_ctx):
    borrower, lender, item = _login_pair(client, app_ctx)
    start, end = _days_around()
    make_request(item, borrower, start, end)

    login(client, email="borrower@kmitl.ac.th")
    client.post(
        f"/rentals/request/{item.id}",
        data={
            "start_date": (end + timedelta(days=1)).isoformat(),
            "end_date": (end + timedelta(days=7)).isoformat(),
        },
        follow_redirects=True,
    )
    assert RentalRequest.query.count() == 2


def test_cannot_request_own_item(client, app_ctx):
    lender = make_user()
    item = make_item(lender)
    login(client)
    start, end = _days_around()
    client.post(
        f"/rentals/request/{item.id}",
        data={"start_date": start.isoformat(), "end_date": end.isoformat()},
        follow_redirects=True,
    )
    assert RentalRequest.query.count() == 0


def test_cannot_request_unavailable_item(client, app_ctx):
    borrower, lender, item = _login_pair(client, app_ctx)
    item.status = "unavailable"
    db.session.commit()
    login(client, email="borrower@kmitl.ac.th")
    start, end = _days_around()
    client.post(
        f"/rentals/request/{item.id}",
        data={"start_date": start.isoformat(), "end_date": end.isoformat()},
        follow_redirects=True,
    )
    assert RentalRequest.query.count() == 0


def test_approve_creates_chat_and_transaction(client, app_ctx):
    borrower, lender, item = _login_pair(client, app_ctx)
    start, end = _days_around()
    request = make_request(item, borrower, start, end)

    login(client, email="lender@kmitl.ac.th")
    response = client.post(f"/rentals/{request.id}/approve", follow_redirects=True)
    assert response.status_code == 200

    db.session.refresh(request)
    assert request.status == "approved"
    assert request.transaction.status == "authorized"
    assert ChatRoom.query.filter_by(rental_request_id=request.id).count() == 1

    # approving twice is not allowed
    client.post(f"/rentals/{request.id}/approve", follow_redirects=True)
    db.session.refresh(request)
    assert request.status == "approved"


def test_only_owner_can_approve(client, app_ctx):
    borrower, lender, item = _login_pair(client, app_ctx)
    start, end = _days_around()
    request = make_request(item, borrower, start, end)

    login(client, email="borrower@kmitl.ac.th")
    client.post(f"/rentals/{request.id}/approve", follow_redirects=True)
    db.session.refresh(request)
    assert request.status == "pending"


def test_third_user_cannot_view_rental(client, app_ctx):
    borrower, lender, item = _login_pair(client, app_ctx)
    start, end = _days_around()
    request = make_request(item, borrower, start, end)

    make_user(email="other@kmitl.ac.th", student_id="6507000030")
    login(client, email="other@kmitl.ac.th")
    assert client.get(f"/rentals/{request.id}").status_code == 403


def test_reject_deletes_chat(client, app_ctx):
    borrower, lender, item = _login_pair(client, app_ctx)
    start, end = _days_around()
    request = make_request(item, borrower, start, end)
    assert ChatRoom.query.count() == 1

    room = ChatRoom.query.first()
    db.session.add(ChatMessage(chat_room_id=room.id, sender_id=borrower.id, message="hi"))
    db.session.commit()

    login(client, email="lender@kmitl.ac.th")
    client.post(f"/rentals/{request.id}/reject", follow_redirects=True)

    db.session.refresh(request)
    assert request.status == "rejected"
    assert request.transaction.status == "refunded"
    assert ChatRoom.query.count() == 0
    assert ChatMessage.query.count() == 0


def test_cancel_by_borrower_deletes_chat(client, app_ctx):
    borrower, lender, item = _login_pair(client, app_ctx)
    start, end = _days_around()
    request = make_request(item, borrower, start, end)

    login(client, email="borrower@kmitl.ac.th")
    client.post(f"/rentals/{request.id}/cancel", follow_redirects=True)

    db.session.refresh(request)
    assert request.status == "cancelled"
    assert ChatRoom.query.count() == 0
    assert ChatMessage.query.count() == 0

    # the lender cannot cancel a borrower's request
    start2, end2 = _days_around(offset_start=30, length=3)
    request2 = make_request(item, borrower, start2, end2)
    login(client, email="lender@kmitl.ac.th")
    client.post(f"/rentals/{request2.id}/cancel", follow_redirects=True)
    db.session.refresh(request2)
    assert request2.status == "pending"


def test_completion_finalises_transaction_and_deletes_chat(client, app_ctx):
    borrower, lender, item = _login_pair(client, app_ctx)
    start, end = _days_around()
    request = make_request(item, borrower, start, end)

    login(client, email="lender@kmitl.ac.th")
    client.post(f"/rentals/{request.id}/approve", follow_redirects=True)
    assert ChatRoom.query.count() == 1

    client.post(f"/rentals/{request.id}/complete", follow_redirects=True)
    db.session.refresh(request)

    assert request.status == "completed"
    assert request.transaction.status == "completed"
    assert ChatRoom.query.count() == 0
    assert ChatMessage.query.count() == 0


def test_auto_sync_activates_and_completes(client, app_ctx):
    borrower, lender, item = _login_pair(client, app_ctx)

    # an approved rental that has already started → becomes active
    future_start = date.today() + timedelta(days=5)
    future_end = date.today() + timedelta(days=9)
    active_request = make_request(item, borrower, future_start, future_end)
    active_request.status = "approved"
    active_request.start_date = date.today() - timedelta(days=2)
    active_request.end_date = date.today() + timedelta(days=3)
    db.session.commit()

    # an active rental that already ended → completed, chat deleted
    second = make_request(item, borrower, date.today() + timedelta(days=20),
                          date.today() + timedelta(days=24))
    second.status = "active"
    second.start_date = date.today() - timedelta(days=10)
    second.end_date = date.today() - timedelta(days=1)
    db.session.commit()

    login(client, email="borrower@kmitl.ac.th")
    client.get("/borrower/dashboard")

    db.session.refresh(active_request)
    db.session.refresh(second)
    assert active_request.status == "active"
    assert second.status == "completed"
    assert ChatRoom.query.filter_by(rental_request_id=second.id).count() == 0


def test_quote_endpoint_reflects_overlap(client, app_ctx):
    borrower, lender, item = _login_pair(client, app_ctx)
    start, end = _days_around()
    make_request(item, borrower, start, end)

    login(client, email="borrower@kmitl.ac.th")
    ok = client.get(
        f"/api/items/{item.id}/quote?start={(end + timedelta(days=1)).isoformat()}"
        f"&end={(end + timedelta(days=3)).isoformat()}"
    )
    assert ok.status_code == 200
    assert ok.get_json()["available"] is True

    clash = client.get(
        f"/api/items/{item.id}/quote?start={(start + timedelta(days=1)).isoformat()}"
        f"&end={(start + timedelta(days=3)).isoformat()}"
    )
    payload = clash.get_json()
    assert payload["available"] is False
    assert "conflict" in payload


def test_borrower_and_lender_price_views(client, app_ctx):
    borrower, lender, item = _login_pair(client, app_ctx)
    start, end = _days_around()
    request = make_request(item, borrower, start, end)

    login(client, email="borrower@kmitl.ac.th")
    page = client.get(f"/rentals/{request.id}").data.decode()
    assert "Borrower service fee" in page
    assert "661.50" in page
    assert "Your earnings" not in page

    login(client, email="lender@kmitl.ac.th")
    page = client.get(f"/rentals/{request.id}").data.decode()
    assert "Your earnings" in page
    assert "567.00" in page
    assert "Borrower service fee" not in page
