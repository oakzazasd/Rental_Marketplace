"""Authentication: KMITL registration rules, hashing, login/logout, access control."""

from helpers import login, make_user, register

from app.extensions import db
from app.models import User


def test_valid_kmitl_registration(client, app_ctx):
    response = register(client, email="Somchai@KMITL.ac.th", student_id="6507011111")
    assert response.status_code == 200
    user = User.query.filter_by(student_id="6507011111").first()
    assert user is not None
    assert user.email == "somchai@kmitl.ac.th"
    # registration logs the user in
    assert b"Hello" in client.get("/dashboard").data


def test_non_kmitl_email_rejected(client, app_ctx):
    for email in ("student@gmail.com", "student@hotmail.com", "student@kmitl.edu"):
        response = register(client, email=email, student_id="6507022222")
        assert b"KMITL" in response.data
        assert User.query.filter_by(email=email).count() == 0


def test_invalid_email_format_rejected(client, app_ctx):
    response = register(client, email="not-an-email", student_id="6507033333")
    assert User.query.count() == 0
    assert response.status_code == 200


def test_duplicate_email_rejected(client, app_ctx):
    make_user(email="dupe@kmitl.ac.th", student_id="6507044444")
    response = register(client, email="dupe@kmitl.ac.th", student_id="6507055555")
    assert b"already exists" in response.data
    assert User.query.count() == 1


def test_short_password_rejected(client, app_ctx):
    response = register(client, email="short@kmitl.ac.th", student_id="6507066666",
                        password="abc", confirm="abc")
    assert User.query.count() == 0
    assert b"between 8 and 128" in response.data or b"at least 8" in response.data


def test_password_mismatch_rejected(client, app_ctx):
    register(client, email="mismatch@kmitl.ac.th", student_id="6507077777",
             password="password123", confirm="password321")
    assert User.query.count() == 0


def test_invalid_student_id_rejected(client, app_ctx):
    register(client, email="sid@kmitl.ac.th", student_id="abc")
    assert User.query.count() == 0


def test_password_is_hashed(client, app_ctx):
    register(client, email="hash@kmitl.ac.th", student_id="6507088888",
             password="supersecret123")
    user = User.query.filter_by(email="hash@kmitl.ac.th").first()
    assert user.password_hash != "supersecret123"
    assert "supersecret123" not in user.password_hash
    assert user.check_password("supersecret123")
    assert not user.check_password("wrongpassword")


def test_login_and_logout(client, app_ctx):
    make_user(email="login@kmitl.ac.th", student_id="6507099999", password="password123")

    bad = client.post("/login", data={"email": "login@kmitl.ac.th", "password": "nope"},
                      follow_redirects=True)
    assert b"Invalid email or password" in bad.data

    good = login(client, email="login@kmitl.ac.th")
    assert b"Welcome back" in good.data

    out = client.get("/logout", follow_redirects=True)
    assert b"logged out" in out.data

    assert client.get("/dashboard").status_code == 302


def test_protected_routes_redirect_anonymous_users(client, app_ctx):
    for path in ("/dashboard", "/items", "/profile", "/borrower/dashboard",
                 "/lender/dashboard", "/lender/items", "/lender/earnings"):
        response = client.get(path)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


def test_users_cannot_see_other_users_private_pages(client, app_ctx):
    make_user(email="owner@kmitl.ac.th", student_id="6507111111", name="Owner")
    from helpers import make_item

    owner = User.query.filter_by(email="owner@kmitl.ac.th").first()
    item = make_item(owner)

    make_user(email="intruder@kmitl.ac.th", student_id="6507222222")
    login(client, email="intruder@kmitl.ac.th")

    assert client.get(f"/lender/items/{item.id}/edit").status_code == 403
    assert client.post(f"/lender/items/{item.id}/delete").status_code == 403
