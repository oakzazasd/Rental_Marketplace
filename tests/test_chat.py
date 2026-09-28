"""Temporary borrower ↔ lender chat: access control, validation and deletion."""

from datetime import date, timedelta

from helpers import login, make_item, make_request, make_user

from app.extensions import db
from app.models import ChatMessage, ChatRoom, RentalRequest


def setup_room(client, app_ctx):
    borrower = make_user(email="borrower@kmitl.ac.th", student_id="6507000010",
                         name="Borrower One")
    lender = make_user(email="lender@kmitl.ac.th", student_id="6507000020",
                       name="Lender One")
    item = make_item(lender, name="Canon Camera", category="Camera")
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=6)
    request = make_request(item, borrower, start, end)
    return borrower, lender, item, request


def send(client, request_id, message):
    return client.post(f"/chat/{request_id}/messages", json={"message": message})


def test_chat_created_with_request(client, app_ctx):
    _, _, _, request = setup_room(client, app_ctx)
    assert ChatRoom.query.filter_by(rental_request_id=request.id).count() == 1
    room = ChatRoom.query.first()
    assert room.borrower_id == request.borrower_id
    assert room.lender_id == request.item.owner_id
    assert room.status == "active"


def test_both_participants_can_open_chat(client, app_ctx):
    borrower, lender, _, request = setup_room(client, app_ctx)

    login(client, email="borrower@kmitl.ac.th")
    assert client.get(f"/chat/{request.id}").status_code == 200

    login(client, email="lender@kmitl.ac.th")
    assert client.get(f"/chat/{request.id}").status_code == 200


def test_third_user_is_denied(client, app_ctx):
    _, _, _, request = setup_room(client, app_ctx)
    make_user(email="intruder@kmitl.ac.th", student_id="6507000030")
    login(client, email="intruder@kmitl.ac.th")

    assert client.get(f"/chat/{request.id}").status_code == 403
    assert send(client, request.id, "let me in").status_code == 403
    assert client.get(f"/chat/{request.id}/messages").status_code == 403
    assert ChatMessage.query.count() == 0


def test_anonymous_user_is_redirected(client, app_ctx):
    _, _, _, request = setup_room(client, app_ctx)
    assert client.get(f"/chat/{request.id}").status_code == 302
    assert send(client, request.id, "hello").status_code == 302


def test_both_participants_can_send_messages(client, app_ctx):
    _, _, _, request = setup_room(client, app_ctx)

    login(client, email="borrower@kmitl.ac.th")
    first = send(client, request.id, "Can I pick it up tomorrow?")
    assert first.status_code == 201

    login(client, email="lender@kmitl.ac.th")
    second = send(client, request.id, "Yes, around 10 AM is fine.")
    assert second.status_code == 201

    assert ChatMessage.query.count() == 2

    login(client, email="borrower@kmitl.ac.th")
    payload = client.get(f"/chat/{request.id}/messages").get_json()
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["message"] == "Can I pick it up tomorrow?"


def test_empty_message_rejected(client, app_ctx):
    _, _, _, request = setup_room(client, app_ctx)
    login(client, email="borrower@kmitl.ac.th")

    assert send(client, request.id, "").status_code == 400
    assert send(client, request.id, "    ").status_code == 400
    assert ChatMessage.query.count() == 0


def test_maximum_message_length_enforced(client, app_ctx):
    _, _, _, request = setup_room(client, app_ctx)
    login(client, email="borrower@kmitl.ac.th")

    response = send(client, request.id, "x" * 2001)
    assert response.status_code == 400
    assert ChatMessage.query.count() == 0

    assert send(client, request.id, "x" * 2000).status_code == 201


def test_html_is_sanitised(client, app_ctx):
    _, _, _, request = setup_room(client, app_ctx)
    login(client, email="borrower@kmitl.ac.th")

    payload = '<script>alert("xss")</script>Hello'
    response = send(client, request.id, payload)
    assert response.status_code == 201

    stored = ChatMessage.query.first()
    # HTML tags are stripped: only plain text is stored
    assert "<script>" not in stored.message
    assert "</script>" not in stored.message
    assert stored.message.endswith("Hello")

    page = client.get(f"/chat/{request.id}").data.decode()
    assert "<script>alert" not in page
    assert "script>alert(" not in page


def test_polling_only_returns_new_messages(client, app_ctx):
    _, _, _, request = setup_room(client, app_ctx)
    login(client, email="borrower@kmitl.ac.th")
    first = send(client, request.id, "first").get_json()["message"]["id"]

    payload = client.get(f"/chat/{request.id}/messages?since={first}").get_json()
    assert payload["messages"] == []

    send(client, request.id, "second")
    payload = client.get(f"/chat/{request.id}/messages?since={first}").get_json()
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["message"] == "second"


def test_unread_indicator_counts(client, app_ctx):
    borrower, lender, _, request = setup_room(client, app_ctx)
    login(client, email="borrower@kmitl.ac.th")
    send(client, request.id, "hello")

    login(client, email="lender@kmitl.ac.th")
    page = client.get("/lender/dashboard").data.decode()
    assert "1 new" in page

    # reading the chat clears the unread count
    client.get(f"/chat/{request.id}")
    payload = client.get(f"/chat/{request.id}/messages").get_json()
    assert payload["unread"] == 0


def test_completed_rental_permanently_deletes_chat(client, app_ctx):
    _, _, _, request = setup_room(client, app_ctx)

    login(client, email="borrower@kmitl.ac.th")
    send(client, request.id, "see you soon")
    assert ChatMessage.query.count() == 1

    login(client, email="lender@kmitl.ac.th")
    client.post(f"/rentals/{request.id}/approve", follow_redirects=True)
    client.post(f"/rentals/{request.id}/complete", follow_redirects=True)

    assert ChatRoom.query.count() == 0
    assert ChatMessage.query.count() == 0
    # messages are gone from the database, not merely hidden
    db.session.commit()
    assert ChatMessage.query.filter_by(chat_room_id=1).count() == 0
    assert client.get(f"/chat/{request.id}").status_code == 404


def test_rejected_request_deletes_chat(client, app_ctx):
    _, _, _, request = setup_room(client, app_ctx)
    login(client, email="borrower@kmitl.ac.th")
    send(client, request.id, "please approve")

    login(client, email="lender@kmitl.ac.th")
    client.post(f"/rentals/{request.id}/reject", follow_redirects=True)

    assert ChatRoom.query.count() == 0
    assert ChatMessage.query.count() == 0
    assert client.get(f"/chat/{request.id}").status_code == 404


def test_cancelled_request_deletes_chat(client, app_ctx):
    _, _, _, request = setup_room(client, app_ctx)
    login(client, email="borrower@kmitl.ac.th")
    send(client, request.id, "changed my mind")
    client.post(f"/rentals/{request.id}/cancel", follow_redirects=True)

    assert ChatRoom.query.count() == 0
    assert ChatMessage.query.count() == 0
    assert client.get(f"/chat/{request.id}").status_code == 404


def test_messages_do_not_exist_for_other_rentals(client, app_ctx):
    """ID manipulation: a user cannot read another rental's conversation."""
    borrower, lender, item, request = setup_room(client, app_ctx)

    other_borrower = make_user(email="second@kmitl.ac.th", student_id="6507000040",
                               name="Second Borrower")
    start = date.today() + timedelta(days=30)
    other_request = make_request(item, other_borrower, start, start + timedelta(days=2))

    login(client, email="borrower@kmitl.ac.th")
    # may access own room
    assert client.get(f"/chat/{request.id}").status_code == 200
    # may not access the other rental's room
    assert client.get(f"/chat/{other_request.id}").status_code == 403
