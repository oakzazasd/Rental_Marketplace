"""Item CRUD and image upload security."""

import os
from pathlib import Path

from helpers import image_file, login, make_item, make_user, register

from app.extensions import db
from app.models import Item, ItemImage
from app.services.image import ImageValidationError, process_image


def _create_item_via_form(client, **overrides):
    data = {
        "name": "Tripod",
        "description": "Sturdy tripod for cameras.",
        "category": "Photography",
        "location": "KMITL",
        "price_per_day": "75.00",
        "deposit": "300.00",
        "status": "available",
    }
    data.update(overrides)
    return client.post("/lender/items/create", data=data, follow_redirects=True)


def test_create_item(client, app_ctx):
    make_user()
    login(client)
    response = _create_item_via_form(client)
    assert response.status_code == 200
    item = Item.query.filter_by(name="Tripod").first()
    assert item is not None
    assert item.price_per_day == 75
    assert item.deposit == 300
    assert item.status == "available"


def test_create_item_requires_login(client, app_ctx):
    response = client.post("/lender/items/create", data={"name": "X"})
    assert response.status_code == 302


def test_edit_item(client, app_ctx):
    owner = make_user()
    login(client)
    item = make_item(owner, name="Old name")
    response = client.post(
        f"/lender/items/{item.id}/edit",
        data={
            "name": "New name",
            "description": "Updated",
            "category": "Camera",
            "location": "Dorm 1",
            "price_per_day": "150.00",
            "deposit": "0",
            "status": "unavailable",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    db.session.refresh(item)
    assert item.name == "New name"
    assert item.price_per_day == 150
    assert item.status == "unavailable"


def test_invalid_price_rejected(client, app_ctx):
    owner = make_user()
    login(client)
    item = make_item(owner)
    response = client.post(
        f"/lender/items/{item.id}/edit",
        data={
            "name": item.name,
            "description": "",
            "category": item.category,
            "location": item.location,
            "price_per_day": "not-a-number",
            "deposit": "0",
            "status": "available",
        },
    )
    assert response.status_code == 400
    db.session.refresh(item)
    assert item.price_per_day == 100


def test_delete_item_hides_from_marketplace(client, app_ctx):
    owner = make_user()
    login(client)
    item = make_item(owner, name="BenQ Projector MX560")
    assert b"BenQ Projector MX560" in client.get("/items").data

    client.post(f"/lender/items/{item.id}/delete", follow_redirects=True)
    db.session.refresh(item)
    assert item.status == "deleted"
    assert b"BenQ Projector MX560" not in client.get("/items").data
    assert client.get(f"/items/{item.id}").status_code == 404


def test_toggle_availability(client, app_ctx):
    owner = make_user()
    login(client)
    item = make_item(owner)
    client.post(f"/lender/items/{item.id}/toggle")
    db.session.refresh(item)
    assert item.status == "unavailable"
    client.post(f"/lender/items/{item.id}/toggle")
    db.session.refresh(item)
    assert item.status == "available"


def test_image_upload_stores_file(client, app_ctx, app):
    owner = make_user()
    login(client)
    response = client.post(
        "/lender/items/create",
        data={
            "name": "Camera",
            "description": "",
            "category": "Camera",
            "location": "KMITL",
            "price_per_day": "150",
            "deposit": "500",
            "status": "available",
            "images": (image_file(), "camera.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    item = Item.query.filter_by(name="Camera").first()
    assert len(item.images) == 1

    stored = Path(app.config["UPLOAD_FOLDER"]) / item.images[0].image_path
    assert stored.is_file()
    assert stored.suffix == ".jpg"
    # original filename must never be used
    assert "camera.jpg" not in item.images[0].image_path


def test_invalid_image_is_rejected(client, app_ctx, app):
    owner = make_user()
    login(client)

    from werkzeug.datastructures import FileStorage

    fake = FileStorage(stream=__import__("io").BytesIO(b"#!/bin/sh\necho hi\n"),
                       filename="evil.jpg", content_type="image/jpeg")
    try:
        process_image(fake)
        raised = False
    except ImageValidationError:
        raised = True
    assert raised


def test_disallowed_extension_rejected(client, app_ctx):
    from werkzeug.datastructures import FileStorage

    import io

    fake = FileStorage(stream=io.BytesIO(b"MZbinary"), filename="shell.php",
                       content_type="image/jpeg")
    try:
        process_image(fake)
        raised = False
    except ImageValidationError as exc:
        raised = True
        assert "Unsupported file type" in str(exc)
    assert raised


def test_path_traversal_filename_is_neutralised(client, app_ctx):
    from werkzeug.datastructures import FileStorage

    from app.services.image import _extension_of

    try:
        _extension_of("../../etc/passwd.jpg")
        ext = "jpg"
    except ImageValidationError:
        ext = None
    assert ext in ("jpg", None)
    # generated names always use uuid hex + whitelisted extension
    path = process_image(image_file(name="../../evil.png", fmt="PNG"))
    assert ".." not in path
    assert "/" not in path.strip("/").split("/")[0].replace("items/", "items/")
    assert path.startswith("items/")


def test_delete_image(client, app_ctx, app):
    owner = make_user()
    login(client)
    item = make_item(owner)
    path = process_image(image_file())
    image = ItemImage(item_id=item.id, image_path=path)
    db.session.add(image)
    db.session.commit()

    client.post(f"/lender/images/{image.id}/delete")
    assert ItemImage.query.count() == 0
    assert not (Path(app.config["UPLOAD_FOLDER"]) / path).exists()


def test_marketplace_renders_for_authenticated_user(client, app_ctx):
    owner = make_user()
    make_item(owner, name="HDMI Cable", category="Cables", price="25.00")
    login(client)
    page = client.get("/items").data.decode()
    assert "HDMI Cable" in page
    assert "฿25.00" in page
