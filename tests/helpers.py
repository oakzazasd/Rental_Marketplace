"""Reusable helpers for the test suite."""

import io

from PIL import Image

from app.extensions import db
from app.models import Item, User


def make_user(email="student001@kmitl.ac.th", student_id="6507000001", name="Test Student",
              password="password123"):
    user = User(name=name, student_id=student_id, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def login(client, email="student001@kmitl.ac.th", password="password123"):
    """Log out any active session first, then log in as the requested user."""
    client.get("/logout", follow_redirects=True)
    return client.post("/login", data={"email": email, "password": password},
                       follow_redirects=True)


def register(client, email="student001@kmitl.ac.th", student_id="6507000001",
             name="Test Student", password="password123", confirm=None):
    return client.post(
        "/register",
        data={
            "name": name,
            "student_id": student_id,
            "email": email,
            "password": password,
            "confirm": confirm or password,
        },
        follow_redirects=True,
    )


def make_item(owner, name="Casio Calculator", category="Calculator", price="100.00",
              deposit="500.00", location="KMITL", status="available",
              description="A reliable scientific calculator."):
    item = Item(
        owner_id=owner.id,
        name=name,
        description=description,
        category=category,
        price_per_day=price,
        deposit=deposit,
        location=location,
        status=status,
    )
    db.session.add(item)
    db.session.commit()
    return item


def image_file(fmt="JPEG", name="photo.jpg", size=(200, 150), color=(240, 120, 40)):
    from werkzeug.datastructures import FileStorage

    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    buffer.seek(0)
    mime = "image/jpeg" if fmt in ("JPEG", "JPG") else f"image/{fmt.lower()}"
    return FileStorage(stream=buffer, filename=name, content_type=mime)


def make_request(item, borrower, start, end):
    """Create a rental request through the real service layer."""
    from app.services import rental as rental_service

    request = rental_service.create_rental_request(item, borrower, start, end)
    db.session.commit()
    return request
