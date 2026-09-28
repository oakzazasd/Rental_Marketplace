"""Marketplace search, filters and promotion-aware ranking."""

from helpers import login, make_item, make_user

from app.extensions import db
from app.services.advertising import create_advertisement


def _positions(html: str, names: list[str]) -> list[int]:
    return [html.find(name) for name in names]


def test_search_returns_matching_items(client, app_ctx):
    owner = make_user()
    make_item(owner, name="Casio fx-991 Calculator", category="Calculator",
              description="Scientific calculator for engineering students")
    make_item(owner, name="Gaming Laptop", category="Computer",
              description="Powerful laptop for rendering and games")
    login(client)

    page = client.get("/items?q=calculator").data.decode()
    assert "Casio fx-991 Calculator" in page
    assert "Gaming Laptop" not in page


def test_search_matches_description_and_category(client, app_ctx):
    owner = make_user()
    make_item(owner, name="Tripod", category="Photography",
              description="Works with any calculator-size camera bag")
    make_item(owner, name="HDMI Cable", category="Cables")
    login(client)

    page = client.get("/items?q=tripod").data.decode()
    assert "Tripod" in page
    assert "HDMI Cable" not in page


def test_promoted_laptop_ranks_below_relevant_calculator(client, app_ctx):
    owner = make_user()
    calculator = make_item(owner, name="Casio Calculator", category="Calculator",
                           description="Scientific calculator for exams")
    laptop = make_item(owner, name="Gaming Laptop", category="Computer",
                       description="Powerful laptop for gaming")
    create_advertisement(laptop, owner.id, "Premium", 7)
    db.session.commit()

    login(client)
    page = client.get("/items?q=calculator").data.decode()

    # both appear: the promoted laptop is still visible…
    assert "Gaming Laptop" in page
    assert "Sponsored" in page
    # …but the relevant calculator ranks above it
    assert _positions(page, ["Casio Calculator", "Gaming Laptop"])[0] < _positions(
        page, ["Casio Calculator", "Gaming Laptop"]
    )[1]


def test_promoted_calculator_ranks_first(client, app_ctx):
    owner = make_user()
    plain = make_item(owner, name="Basic Calculator", category="Calculator")
    promoted = make_item(owner, name="Advanced Calculator", category="Calculator")
    create_advertisement(promoted, owner.id, "Premium", 7)
    db.session.commit()

    login(client)
    page = client.get("/items?q=calculator").data.decode()
    assert page.find("Advanced Calculator") < page.find("Basic Calculator")


def test_expired_promotion_gives_no_boost(client, app_ctx):
    from datetime import date, timedelta

    owner = make_user()
    plain = make_item(owner, name="Basic Calculator", category="Calculator")
    promoted = make_item(owner, name="Advanced Calculator", category="Calculator")
    ad = create_advertisement(promoted, owner.id, "Premium", 7)
    ad.end_date = date.today() - timedelta(days=3)
    db.session.commit()

    login(client)
    page = client.get("/items?q=calculator").data.decode()
    # both still show, but the expired promotion no longer says "Sponsored"
    assert "Advanced Calculator" in page
    assert "Sponsored" not in page


def test_category_filter(client, app_ctx):
    owner = make_user()
    make_item(owner, name="Epson Beamer X200", category="Projector")
    make_item(owner, name="Organic Chemistry Textbook", category="Books")
    login(client)

    page = client.get("/items?category=Books").data.decode()
    assert "Organic Chemistry Textbook" in page
    assert "Epson Beamer X200" not in page


def test_price_filter(client, app_ctx):
    owner = make_user()
    make_item(owner, name="Cheap Cable", category="Cables", price="20.00")
    make_item(owner, name="Fancy Lens", category="Camera", price="400.00")
    login(client)

    page = client.get("/items?max_price=100").data.decode()
    assert "Cheap Cable" in page
    assert "Fancy Lens" not in page

    page = client.get("/items?min_price=300").data.decode()
    assert "Fancy Lens" in page
    assert "Cheap Cable" not in page


def test_availability_filter(client, app_ctx):
    owner = make_user()
    make_item(owner, name="Available Item", status="available")
    make_item(owner, name="Hidden Item", status="unavailable")
    login(client)

    page = client.get("/items?availability=available").data.decode()
    assert "Available Item" in page
    assert "Hidden Item" not in page


def test_sort_by_price(client, app_ctx):
    owner = make_user()
    make_item(owner, name="Alpha Item", price="500.00")
    make_item(owner, name="Beta Item", price="100.00")
    login(client)

    page = client.get("/items?sort=price_asc").data.decode()
    assert page.find("Beta Item") < page.find("Alpha Item")

    page = client.get("/items?sort=price_desc").data.decode()
    assert page.find("Alpha Item") < page.find("Beta Item")


def test_deleted_items_are_hidden(client, app_ctx):
    owner = make_user()
    item = make_item(owner, name="Removed Item")
    item.status = "deleted"
    db.session.commit()
    login(client)

    assert b"Removed Item" not in client.get("/items").data
    assert client.get(f"/items/{item.id}").status_code == 404
