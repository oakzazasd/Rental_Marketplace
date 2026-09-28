"""Seed demo data for local development.

    python seed.py            # add demo data (safe to re-run)
    python seed.py --reset    # drop and recreate every table first

Demo accounts use fake `.test` addresses so no real mailbox is required:

    student001@example.test / password123   (borrower + lender)
    student002@example.test / password123   (borrower)
    lender001@example.test   / password123   (lender)

Production registration still enforces @kmitl.ac.th — seeding inserts rows
directly through the ORM and bypasses that check on purpose.
"""

import argparse
import io
import random
from datetime import date, timedelta

from PIL import Image, ImageDraw

from app import create_app
from app.extensions import db
from app.models import (
    Advertisement,
    ChatMessage,
    ChatRoom,
    Item,
    ItemImage,
    RentalRequest,
    Transaction,
    User,
)
from app.seed_config import ensure_default_config
from app.services import advertising as ad_service
from app.services import chat as chat_service
from app.services import rental as rental_service

PASSWORD = "password123"

DEMO_USERS = [
    ("Napat Srisai", "6507000001", "student001@example.test"),
    ("Ploy Chantha", "6507000002", "student002@example.test"),
    ("Kittipong Jaidee", "6507000003", "lender001@example.test"),
    ("Anong Ratsami", "6507000004", "lender002@example.test"),
]

DEMO_ITEMS = [
    # owner index, name, category, price, deposit, location, description
    (2, "Casio fx-991EX Calculator", "Calculator", 25.00, 100.00, "KMITL Engineering Building",
     "Original Casio fx-991EX Classwiz. Perfect for engineering exams. Includes protective case."),
    (0, "Canon EOS M50 Camera", "Camera", 250.00, 1500.00, "KMITL Dormitory 3",
     "Mirrorless camera with 15-45mm kit lens, battery and 64GB SD card. Great for graduation photos."),
    (2, "Manfrotto Compact Tripod", "Photography", 60.00, 300.00, "KMITL Library",
     "Lightweight aluminium tripod, fits in a backpack, holds up to 3kg."),
    (1, "MacBook Air M1", "Computer", 350.00, 3000.00, "KMITL Dormitory 1",
     "8GB RAM / 256GB SSD. Charged and factory reset before every handover."),
    (3, "Epson EB-X06 Projector", "Projector", 300.00, 1000.00, "KMITL Building 4",
     "XGA projector with HDMI cable and remote. 3,600 lumens — works in a bright room."),
    (0, "HDMI Cable 3m 4K", "Cables", 15.00, 0.00, "KMITL Engineering Building",
     "Braided HDMI 2.0 cable, 3 metres, supports 4K@60Hz."),
    (2, "Engineering Mathematics Textbook", "Books", 35.00, 0.00, "KMITL Bookshop",
     "Thomas' Calculus, 14th edition. Some highlighting in chapter 3."),
    (1, "Arduino Starter Kit", "Lab Equipment", 120.00, 400.00, "KMITL Dormitory 1",
     "Uno board, sensors, breadboard and jumper wires for lab projects."),
    (3, "Drill + Bit Set", "Tools", 90.00, 500.00, "KMITL Workshop",
     "Cordless drill with a full bit set. Only for on-campus use."),
    (0, "Badminton Racket Pair", "Sports Equipment", 40.00, 100.00, "KMITL Sports Center",
     "Two rackets with a tube of shuttles. Freshly strung at 24lbs."),
]

PLACEHOLDER_COLORS = [
    (249, 115, 22),
    (234, 88, 12),
    (37, 99, 235),
    (22, 163, 74),
    (124, 58, 237),
    (202, 138, 4),
]


def placeholder_image(label: str, color):
    image = Image.new("RGB", (900, 675), color)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([40, 40, 860, 635], radius=36, fill=(255, 255, 255))
    text = label[:26]
    draw.text((90, 300), text, fill=color)
    draw.text((90, 350), "KMITL Rent demo image", fill=(107, 114, 128))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    return buffer


def attach_images(item, app, count=1):
    from werkzeug.datastructures import FileStorage

    for index in range(count):
        color = PLACEHOLDER_COLORS[(hash(item.name) + index) % len(PLACEHOLDER_COLORS)]
        stream = placeholder_image(item.name, color)
        storage = FileStorage(stream=stream, filename=f"{item.id}-{index}.jpg",
                              content_type="image/jpeg")
        from app.services.image import process_image

        path = process_image(storage, subfolder="items")
        db.session.add(ItemImage(item_id=item.id, image_path=path))
    db.session.commit()


def upsert_users():
    users = {}
    for name, student_id, email in DEMO_USERS:
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(name=name, student_id=student_id, email=email)
            user.set_password(PASSWORD)
            db.session.add(user)
            db.session.flush()
        users[email] = user
    db.session.commit()
    return users


def upsert_items(users):
    items = []
    for owner_index, name, category, price, deposit, location, description in DEMO_ITEMS:
        owner = users[DEMO_USERS[owner_index][2]]
        item = Item.query.filter_by(name=name).first()
        if item is None:
            item = Item(
                owner=owner,
                name=name,
                description=description,
                category=category,
                price_per_day=price,
                deposit=deposit,
                location=location,
                status="available",
            )
            db.session.add(item)
            db.session.flush()
        items.append(item)
    db.session.commit()

    for item in items:
        if not item.images:
            attach_images(item, None, count=2 if item.deposit > 0 else 1)
    return items


def seed_rentals(users, items):
    if RentalRequest.query.count() > 0:
        return

    borrower = users["student001@example.test"]
    borrower2 = users["student002@example.test"]

    # 1) pending request with an open chat
    first = items[0]
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=6)
    pending = rental_service.create_rental_request(first, borrower, start, end)
    db.session.flush()
    room = chat_service.ensure_chat(pending)
    db.session.flush()
    db.session.add_all(
        [
            ChatMessage(chat_room_id=room.id, sender_id=borrower.id,
                        message="Sawasdee krub! Can I borrow the calculator for exams?"),
            ChatMessage(chat_room_id=room.id, sender_id=first.owner_id,
                        message="Sure — pick it up at the Engineering Building after 10 AM."),
            ChatMessage(chat_room_id=room.id, sender_id=borrower.id,
                        message="Perfect, see you then. Thank you!"),
        ]
    )
    db.session.flush()
    # borrower read the replies, lender has not
    chat_service.mark_read(room, borrower)

    # 2) approved (upcoming) rental
    camera = items[1]
    start2 = date.today() + timedelta(days=10)
    end2 = start2 + timedelta(days=4)
    approved = rental_service.create_rental_request(camera, borrower2, start2, end2)
    rental_service.approve_request(approved, camera.owner)
    db.session.flush()

    # 3) completed rental with a settled transaction + deleted chat
    tripod = items[2]
    start3 = date.today() + timedelta(days=40)
    end3 = start3 + timedelta(days=4)
    finished = rental_service.create_rental_request(tripod, borrower, start3, end3)
    rental_service.approve_request(finished, tripod.owner)
    db.session.flush()
    # back-date the rental so it already happened
    finished.start_date = date.today() - timedelta(days=12)
    finished.end_date = date.today() - timedelta(days=8)
    finished.status = "completed"
    finished.transaction.status = "completed"
    db.session.flush()
    chat_service.close_and_delete_chat(finished)
    db.session.flush()

    db.session.commit()


def seed_promotions(users, items):
    if Advertisement.query.count() > 0:
        return

    calculator = items[0]
    camera = items[1]
    ad_service.create_advertisement(calculator, calculator.owner_id, "Premium", 7)
    ad_service.create_advertisement(camera, camera.owner_id, "Standard", 14)
    db.session.commit()


def main():
    parser = argparse.ArgumentParser(description="Seed demo data")
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if args.reset:
            print("Dropping all tables…")
            db.drop_all()
        db.create_all()
        ensure_default_config()

        users = upsert_users()
        items = upsert_items(users)
        seed_rentals(users, items)
        seed_promotions(users, items)

        counts = {
            "users": User.query.count(),
            "items": Item.query.count(),
            "images": ItemImage.query.count(),
            "rentals": RentalRequest.query.count(),
            "transactions": Transaction.query.count(),
            "chats": ChatRoom.query.count(),
            "messages": ChatMessage.query.count(),
            "ads": Advertisement.query.count(),
        }
        print("Seed complete:")
        for key, value in counts.items():
            print(f"  {key:<12} {value}")
        print()
        print("Demo logins (password: password123):")
        for _, _, email in DEMO_USERS:
            print(f"  {email}")
        print()
        print("Run the app:  python run.py")


if __name__ == "__main__":
    main()
