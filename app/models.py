"""Database models for the KMITL student rental marketplace."""

from datetime import date, datetime
from decimal import Decimal

from flask_login import UserMixin
from sqlalchemy import Numeric, UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from app import constants as C
from app.extensions import db
from app.utils import money


class Money(Numeric):
    """Decimal money column that binds cleanly on SQLite and PostgreSQL."""

    def __init__(self, precision=12, scale=2):
        super().__init__(precision=precision, scale=scale, asdecimal=True)

    def bind_processor(self, dialect):
        if dialect.name != "sqlite":
            return None

        def process(value):
            if value is None:
                return None
            if not isinstance(value, Decimal):
                value = Decimal(str(value))
            return str(value.quantize(Decimal("0.01")))

        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            if not isinstance(value, Decimal):
                value = Decimal(str(value))
            return value.quantize(Decimal("0.01"))

        return process


def utcnow() -> datetime:
    return datetime.utcnow()


def today() -> date:
    return date.today()


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    items = db.relationship(
        "Item", back_populates="owner", lazy="dynamic", cascade="all, delete-orphan"
    )
    rental_requests = db.relationship(
        "RentalRequest",
        back_populates="borrower",
        lazy="dynamic",
        foreign_keys="RentalRequest.borrower_id",
        cascade="all, delete-orphan",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email}>"


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------
class Item(db.Model):
    __tablename__ = "items"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = db.Column(db.String(150), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False, default="")
    category = db.Column(db.String(60), nullable=False, index=True)
    price_per_day = db.Column(Money(), nullable=False, default=Decimal("0.00"))
    deposit = db.Column(Money(), nullable=False, default=Decimal("0.00"))
    location = db.Column(db.String(150), nullable=False, default="KMITL")
    status = db.Column(db.String(20), nullable=False, default="available", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    owner = db.relationship("User", back_populates="items")
    images = db.relationship(
        "ItemImage",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="ItemImage.created_at.asc()",
        lazy="selectin",
    )
    rental_requests = db.relationship(
        "RentalRequest", back_populates="item", lazy="dynamic", cascade="all, delete-orphan"
    )
    advertisements = db.relationship(
        "Advertisement", back_populates="item", lazy="dynamic", cascade="all, delete-orphan"
    )

    @property
    def is_available(self) -> bool:
        return self.status == "available"

    @property
    def is_listed(self) -> bool:
        return self.status != "deleted"

    @property
    def primary_image(self):
        return self.images[0] if self.images else None

    @property
    def image_url(self):
        image = self.primary_image
        if image is None:
            return None
        return f"/uploads/{image.image_path}"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Item {self.name}>"


class ItemImage(db.Model):
    __tablename__ = "item_images"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(
        db.Integer, db.ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image_path = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    item = db.relationship("Item", back_populates="images")


# ---------------------------------------------------------------------------
# Rental request + transaction
# ---------------------------------------------------------------------------
class RentalRequest(db.Model):
    __tablename__ = "rental_requests"
    __table_args__ = (
        db.Index("ix_rental_requests_item_status", "item_id", "status"),
        db.Index("ix_rental_requests_borrower_status", "borrower_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(
        db.Integer, db.ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    borrower_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    number_of_days = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    item = db.relationship("Item", back_populates="rental_requests")
    borrower = db.relationship("User", back_populates="rental_requests", foreign_keys=[borrower_id])
    transaction = db.relationship(
        "Transaction",
        back_populates="rental_request",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    chat_room = db.relationship(
        "ChatRoom",
        back_populates="rental_request",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def lender_id(self) -> int:
        return self.item.owner_id

    @property
    def is_active(self) -> bool:
        return self.status in ("approved", "active")

    @property
    def can_chat(self) -> bool:
        return self.status in C.RENTAL_CHAT_STATUSES


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    rental_request_id = db.Column(
        db.Integer,
        db.ForeignKey("rental_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    base_amount = db.Column(Money(), nullable=False, default=Decimal("0.00"))
    discount_rate = db.Column(Numeric(6, 4), nullable=False, default=Decimal("0"))
    discount_amount = db.Column(Money(), nullable=False, default=Decimal("0.00"))
    rental_subtotal = db.Column(Money(), nullable=False, default=Decimal("0.00"))
    borrower_service_fee_rate = db.Column(Numeric(6, 4), nullable=False, default=Decimal("0"))
    borrower_service_fee = db.Column(Money(), nullable=False, default=Decimal("0.00"))
    lender_platform_fee_rate = db.Column(Numeric(6, 4), nullable=False, default=Decimal("0"))
    lender_platform_fee = db.Column(Money(), nullable=False, default=Decimal("0.00"))
    borrower_total = db.Column(Money(), nullable=False, default=Decimal("0.00"))
    lender_payout = db.Column(Money(), nullable=False, default=Decimal("0.00"))
    platform_revenue = db.Column(Money(), nullable=False, default=Decimal("0.00"))
    deposit = db.Column(Money(), nullable=False, default=Decimal("0.00"))
    currency = db.Column(db.String(10), nullable=False, default=C.CURRENCY)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    rental_request = db.relationship("RentalRequest", back_populates="transaction")

    @property
    def amount_required(self) -> Decimal:
        return money(self.borrower_total + self.deposit)


# ---------------------------------------------------------------------------
# Pricing configuration
# ---------------------------------------------------------------------------
class PricingConfig(db.Model):
    __tablename__ = "pricing_configs"

    id = db.Column(db.Integer, primary_key=True)
    borrower_service_fee_rate = db.Column(Numeric(6, 4), nullable=False, default=Decimal("0.05"))
    lender_platform_fee_rate = db.Column(Numeric(6, 4), nullable=False, default=Decimal("0.10"))
    currency = db.Column(db.String(10), nullable=False, default=C.CURRENCY)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class RentalDiscount(db.Model):
    __tablename__ = "rental_discounts"

    id = db.Column(db.Integer, primary_key=True)
    minimum_days = db.Column(db.Integer, nullable=False)
    maximum_days = db.Column(db.Integer, nullable=True)  # NULL means "no upper limit"
    discount_rate = db.Column(Numeric(6, 4), nullable=False, default=Decimal("0"))
    active = db.Column(db.Boolean, nullable=False, default=True)

    @property
    def label(self) -> str:
        pct = f"{(self.discount_rate * 100).normalize():f}".rstrip("0").rstrip(".")
        if self.maximum_days is None:
            return f"{self.minimum_days}+ days → {pct}%"
        if self.minimum_days == self.maximum_days:
            return f"{self.minimum_days} day → {pct}%"
        return f"{self.minimum_days}–{self.maximum_days} days → {pct}%"


# ---------------------------------------------------------------------------
# Advertising
# ---------------------------------------------------------------------------
class Advertisement(db.Model):
    __tablename__ = "advertisements"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(
        db.Integer, db.ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    promotion_level = db.Column(db.String(30), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    daily_price = db.Column(Money(), nullable=False, default=Decimal("0.00"))
    total_price = db.Column(Money(), nullable=False, default=Decimal("0.00"))
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    item = db.relationship("Item", back_populates="advertisements")
    owner = db.relationship("User", foreign_keys=[owner_id])

    @property
    def is_running(self) -> bool:
        return self.status == "active" and self.start_date <= today() <= self.end_date


class PromotionLevel(db.Model):
    __tablename__ = "promotion_levels"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)
    ranking_weight = db.Column(db.Integer, nullable=False, default=0)
    price_multiplier = db.Column(Numeric(8, 4), nullable=False, default=Decimal("1"))
    active = db.Column(db.Boolean, nullable=False, default=True)


class AdvertisingConfig(db.Model):
    __tablename__ = "advertising_configs"

    id = db.Column(db.Integer, primary_key=True)
    base_daily_price = db.Column(Money(), nullable=False, default=Decimal("20.00"))
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class CategoryCompetitionConfig(db.Model):
    __tablename__ = "category_competition_configs"

    id = db.Column(db.Integer, primary_key=True)
    minimum_listings = db.Column(db.Integer, nullable=False)
    maximum_listings = db.Column(db.Integer, nullable=True)  # NULL = no upper limit
    competition_multiplier = db.Column(Numeric(8, 4), nullable=False, default=Decimal("1"))

    __table_args__ = (
        UniqueConstraint("minimum_listings", name="uq_competition_minimum"),
    )


# ---------------------------------------------------------------------------
# Temporary rental chat
# ---------------------------------------------------------------------------
class ChatRoom(db.Model):
    __tablename__ = "chat_rooms"

    id = db.Column(db.Integer, primary_key=True)
    rental_request_id = db.Column(
        db.Integer,
        db.ForeignKey("rental_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    borrower_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lender_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default=C.CHAT_ACTIVE, index=True)
    last_read_by_borrower = db.Column(db.DateTime, nullable=True)
    last_read_by_lender = db.Column(db.DateTime, nullable=True)

    rental_request = db.relationship("RentalRequest", back_populates="chat_room")
    borrower = db.relationship("User", foreign_keys=[borrower_id])
    lender = db.relationship("User", foreign_keys=[lender_id])
    messages = db.relationship(
        "ChatMessage",
        back_populates="room",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at.asc()",
        lazy="dynamic",
        passive_deletes=True,
    )

    def participant_ids(self):
        return {self.borrower_id, self.lender_id}


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"
    __table_args__ = (db.Index("ix_chat_messages_room_created", "chat_room_id", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    chat_room_id = db.Column(
        db.Integer, db.ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    room = db.relationship("ChatRoom", back_populates="messages")
    sender = db.relationship("User", foreign_keys=[sender_id])


def load_user(user_id: str):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
