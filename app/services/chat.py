"""Temporary borrower ↔ lender chat lifecycle.

The chat room belongs to exactly one rental request. It is created when the
request is created and physically deleted (messages first, then the room) as
soon as the rental is completed, rejected or cancelled.

There is no permanent messaging system in this application on purpose.
"""

import re
from datetime import datetime

from flask import current_app

from app import constants as C
from app.extensions import db
from app.models import ChatMessage, ChatRoom, RentalRequest, User


class ChatError(Exception):
    """User facing chat error."""


_TAG_RE = re.compile(r"<[^>]*>")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def max_message_length() -> int:
    return int(current_app.config.get("MAX_MESSAGE_LENGTH", C.DEFAULT_MAX_MESSAGE_LENGTH))


def sanitize_message(raw: str) -> str:
    """Return plain text safe to store: no HTML tags, no control characters."""
    if raw is None:
        return ""
    text = str(raw)
    text = _TAG_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    text = text.replace("\r\n", "\n").strip()
    return text


def validate_message(raw: str) -> str:
    text = sanitize_message(raw)
    if not text:
        raise ChatError("Message cannot be empty.")
    limit = max_message_length()
    if len(text) > limit:
        raise ChatError(f"Message is too long (maximum {limit} characters).")
    return text


def ensure_chat(rental_request: RentalRequest) -> ChatRoom:
    """Create the chat room for a rental request if it does not exist yet."""
    if rental_request.chat_room is not None:
        return rental_request.chat_room
    room = ChatRoom(
        rental_request_id=rental_request.id,
        borrower_id=rental_request.borrower_id,
        lender_id=rental_request.item.owner_id,
        status=C.CHAT_ACTIVE,
    )
    db.session.add(room)
    rental_request.chat_room = room
    db.session.flush()
    return room


def room_exists(rental_request_id: int) -> bool:
    return ChatRoom.query.filter_by(rental_request_id=rental_request_id).first() is not None


def close_and_delete_chat(rental_request) -> None:
    """Permanently delete chat messages and the room for a rental request.

    Accepts either a RentalRequest or a rental request id. Safe to call when
    no chat exists.
    """
    if isinstance(rental_request, RentalRequest):
        request_id = rental_request.id
        room = ChatRoom.query.filter_by(rental_request_id=request_id).first()
    else:
        request_id = int(rental_request)
        room = ChatRoom.query.filter_by(rental_request_id=request_id).first()

    if room is None:
        return

    room.status = C.CHAT_CLOSED
    room.closed_at = datetime.utcnow()
    db.session.flush()

    ChatMessage.query.filter_by(chat_room_id=room.id).delete(synchronize_session=False)
    db.session.delete(room)
    db.session.flush()


def get_room_for_request(rental_request_id: int) -> ChatRoom | None:
    return ChatRoom.query.filter_by(rental_request_id=rental_request_id).first()


def user_can_access(room: ChatRoom, user) -> bool:
    if room is None or user is None or not user.is_authenticated:
        return False
    if room.status != C.CHAT_ACTIVE:
        return False
    return user.id in room.participant_ids()


def other_participant(room: ChatRoom, user) -> User | None:
    if user.id == room.borrower_id:
        return room.lender
    return room.borrower


def mark_read(room: ChatRoom, user) -> None:
    now = datetime.utcnow()
    if user.id == room.borrower_id:
        room.last_read_by_borrower = now
    elif user.id == room.lender_id:
        room.last_read_by_lender = now


def _last_read(room: ChatRoom, user) -> datetime | None:
    if user.id == room.borrower_id:
        return room.last_read_by_borrower
    if user.id == room.lender_id:
        return room.last_read_by_lender
    return None


def unread_count_for_room(room: ChatRoom, user) -> int:
    if room.status != C.CHAT_ACTIVE:
        return 0
    if user.id not in room.participant_ids():
        return 0
    last_read = _last_read(room, user)
    query = ChatMessage.query.filter(
        ChatMessage.chat_room_id == room.id,
        ChatMessage.sender_id != user.id,
    )
    if last_read is not None:
        query = query.filter(ChatMessage.created_at > last_read)
    return query.count()


def unread_count(user) -> int:
    """Total unread rental messages for a user (used by the navbar badge)."""
    if user is None or not user.is_authenticated:
        return 0
    rooms = ChatRoom.query.filter(
        ChatRoom.status == C.CHAT_ACTIVE,
        db.or_(ChatRoom.borrower_id == user.id, ChatRoom.lender_id == user.id),
    ).all()
    total = 0
    for room in rooms:
        total += unread_count_for_room(room, user)
    return total


def post_message(room: ChatRoom, user, raw_text: str) -> ChatMessage:
    if not user_can_access(room, user):
        raise ChatError("You are not allowed to send messages in this chat.")
    text = validate_message(raw_text)
    message = ChatMessage(chat_room_id=room.id, sender_id=user.id, message=text)
    db.session.add(message)
    mark_read(room, user)
    db.session.flush()
    return message


def messages_since(room: ChatRoom, user, since_id: int = 0) -> list[ChatMessage]:
    if not user_can_access(room, user):
        raise ChatError("You are not allowed to read this chat.")
    query = (
        ChatMessage.query.filter(ChatMessage.chat_room_id == room.id, ChatMessage.id > since_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )
    mark_read(room, user)
    return query


def serialize_message(message: ChatMessage) -> dict:
    return {
        "id": message.id,
        "sender_id": message.sender_id,
        "sender_name": message.sender.name if message.sender else "Unknown",
        "message": message.message,
        "created_at": message.created_at.strftime("%d %b %Y, %H:%M"),
    }
