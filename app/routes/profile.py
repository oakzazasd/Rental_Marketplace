"""User profile."""

import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Item, RentalRequest, User

blueprint = Blueprint("profile", __name__)

STUDENT_ID_RE = re.compile(r"^\d{8,12}$")


@blueprint.route("/profile", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        student_id = (request.form.get("student_id") or "").strip()

        errors = []
        if not name or len(name) > 120:
            errors.append("Please provide your full name (max 120 characters).")
        if not STUDENT_ID_RE.match(student_id):
            errors.append("Student ID must be 8–12 digits.")
        else:
            existing = User.query.filter_by(student_id=student_id).first()
            if existing and existing.id != current_user.id:
                errors.append("That student ID is already in use.")

        if errors:
            for message in errors:
                flash(message, "danger")
            return redirect(url_for("profile.index"))

        current_user.name = name
        current_user.student_id = student_id
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("profile.index"))

    listed_items = Item.query.filter(
        Item.owner_id == current_user.id, Item.status != "deleted"
    ).count()
    rentals_as_borrower = RentalRequest.query.filter_by(borrower_id=current_user.id).count()
    rentals_as_lender = (
        RentalRequest.query.join(Item, Item.id == RentalRequest.item_id)
        .filter(Item.owner_id == current_user.id)
        .count()
    )

    return render_template(
        "profile.html",
        listed_items=listed_items,
        rentals_as_borrower=rentals_as_borrower,
        rentals_as_lender=rentals_as_lender,
    )
