import shutil
import tempfile

import pytest

from app import create_app
from app.extensions import db
from config import TestConfig


class _TestConfig(TestConfig):
    UPLOAD_FOLDER = tempfile.mkdtemp(prefix="rental_test_uploads_")
    WTF_CSRF_ENABLED = False


@pytest.fixture(scope="session")
def app():
    application = create_app(_TestConfig)
    yield application
    shutil.rmtree(_TestConfig.UPLOAD_FOLDER, ignore_errors=True)


def _prepare_db():
    from app.seed_config import ensure_default_config

    db.session.remove()
    db.drop_all()
    db.create_all()
    ensure_default_config()


@pytest.fixture()
def client(app):
    with app.app_context():
        db.session.remove()
        db.drop_all()
        _prepare_db()
    yield app.test_client()
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def app_ctx(app):
    with app.app_context():
        _prepare_db()
        yield


@pytest.fixture()
def borrower_and_lender(client, app_ctx):
    from helpers import make_user

    borrower = make_user(email="borrower@kmitl.ac.th", student_id="6507000010",
                         name="Borrower One")
    lender = make_user(email="lender@kmitl.ac.th", student_id="6507000020",
                       name="Lender One")
    return borrower, lender
