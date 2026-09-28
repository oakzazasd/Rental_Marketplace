"""Temporary rental chat: page + polling endpoints."""

from flask import Blueprint, abort, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from app.extensions import db
from app.models import ChatRoom, RentalRequest
from app.services import chat as chat_service

blueprint = Blueprint("chat", __name__)


def _get_room(request_id: int) -> ChatRoom:
    rental_request = db.session.get(RentalRequest, request_id)
    if rental_request is None:
        abort(404)
    if current_user.id not in {rental_request.borrower_id, rental_request.item.owner_id}:
        abort(403)

    room = chat_service.get_room_for_request(request_id)
    if room is None:
        abort(404)
    if not chat_service.user_can_access(room, current_user):
        abort(403)
    return room


@blueprint.route("/<int:request_id>")
@login_required
def index(request_id):
    room = _get_room(request_id)
    rental_request = room.rental_request
    item = rental_request.item
    other = chat_service.other_participant(room, current_user)

    messages = room.messages.all()
    db.session.commit()  # persists the "last read" marker set by mark_read

    return render_template(
        "chat/index.html",
        room=room,
        rental_request=rental_request,
        item=item,
        other=other,
        messages=messages,
        max_length=int(current_app.config.get("MAX_MESSAGE_LENGTH", 2000)),
    )


@blueprint.route("/<int:request_id>/messages", methods=["GET"])
@login_required
def messages(request_id):
    room = _get_room(request_id)
    try:
        since_id = int(request.args.get("since", 0))
    except ValueError:
        since_id = 0

    try:
        new_messages = chat_service.messages_since(room, current_user, since_id)
    except chat_service.ChatError as exc:
        return jsonify({"error": str(exc)}), 403

    unread = chat_service.unread_count_for_room(room, current_user)
    other = chat_service.other_participant(room, current_user)
    db.session.commit()

    return jsonify(
        {
            "messages": [chat_service.serialize_message(m) for m in new_messages],
            "unread": unread,
            "status": room.status,
            "other_name": other.name if other else "",
            "item_name": room.rental_request.item.name,
        }
    )


@blueprint.route("/<int:request_id>/messages", methods=["POST"])
@login_required
def send(request_id):
    room = _get_room(request_id)
    payload = request.get_json(silent=True)
    if payload is not None:
        raw = payload.get("message", "")
    else:
        raw = request.form.get("message", "")

    try:
        message = chat_service.post_message(room, current_user, raw)
        db.session.commit()
    except chat_service.ChatError as exc:
        db.session.rollback()
        status = 403 if "not allowed" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status

    return jsonify({"message": chat_service.serialize_message(message)}), 201
