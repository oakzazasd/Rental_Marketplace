"""Registration, login and logout."""

import re
from urllib.parse import urljoin, urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length, ValidationError

from app import constants as C
from app.extensions import db
from app.models import User

blueprint = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STUDENT_ID_RE = re.compile(r"^\d{8,12}$")
MIN_PASSWORD_LENGTH = 8


def _allowed_domain() -> str:
    return C.ALLOWED_EMAIL_DOMAIN


class RegisterForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    student_id = StringField("Student ID", validators=[DataRequired(), Length(max=20)])
    email = StringField("KMITL email", validators=[DataRequired(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=MIN_PASSWORD_LENGTH, max=128)])
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords do not match.")],
    )
    submit = SubmitField("Create account")

    def validate_email(self, field):
        email = (field.data or "").strip().lower()
        if not EMAIL_RE.match(email):
            raise ValidationError("Please enter a valid email address.")
        if not email.endswith(_allowed_domain()):
            raise ValidationError(
                f"Only KMITL email addresses are allowed (must end with {_allowed_domain()})."
            )
        if User.query.filter(db.func.lower(User.email) == email).first():
            raise ValidationError("An account with this email already exists.")

    def validate_student_id(self, field):
        student_id = (field.data or "").strip()
        if not STUDENT_ID_RE.match(student_id):
            raise ValidationError("Student ID must be 8–12 digits.")
        if User.query.filter_by(student_id=student_id).first():
            raise ValidationError("An account with this student ID already exists.")


class LoginForm(FlaskForm):
    email = StringField("KMITL email", validators=[DataRequired(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember me")
    submit = SubmitField("Log in")


def _safe_next(target) -> str | None:
    """Only allow local redirects after login (prevents open redirects)."""
    if not target:
        return None
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    if test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc:
        return target
    return None

@blueprint.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = RegisterForm()
    if form.validate_on_submit():
        user = User(
            name=form.name.data.strip(),
            student_id=form.student_id.data.strip(),
            email=form.email.data.strip().lower(),
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Welcome to KMITL Rent! Your account has been created.", "success")
        # E-mail verification hook: when a verification service is added, gate
        # the redirect here (e.g. send the user to /verify/<token> first).
        return redirect(_safe_next(request.args.get("next")) or url_for("dashboard.index"))

    if request.method == "POST":
        flash("Please correct the errors below.", "danger")
    return render_template("auth/register.html", form=form)


@blueprint.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    if form.validate_on_submit():
        email = (form.email.data or "").strip().lower()
        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user is None or not user.check_password(form.password.data):
            flash("Invalid email or password.", "danger")
        else:
            login_user(user, remember=form.remember.data)
            flash(f"Welcome back, {user.name}!", "success")
            return redirect(_safe_next(request.args.get("next")) or url_for("dashboard.index"))

    if request.method == "POST":
        flash("Please correct the errors below.", "danger")
    return render_template("auth/login.html", form=form)


@blueprint.route("/logout", methods=["POST", "GET"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
