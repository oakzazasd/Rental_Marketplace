"""Flask application factory."""

import os
from pathlib import Path

from flask import Flask, render_template, send_from_directory
from flask_migrate import Migrate
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app import constants as C
from app.extensions import csrf, db, login_manager
from app.models import User, load_user
from app.seed_config import ensure_default_config
from app.utils import register_jinja_helpers

try:  # pragma: no cover - only used when running from a different cwd
    from config import Config, TestConfig  # type: ignore
except ImportError:  # pragma: no cover
    from config import Config  # type: ignore

    TestConfig = Config


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key constraints on SQLite (needed for ON DELETE CASCADE)."""
    module = type(dbapi_connection).__module__ or ""
    if "sqlite" in module:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_app(config_object=None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object or Config)

    upload_folder = Path(app.config["UPLOAD_FOLDER"])
    if not upload_folder.is_absolute():
        upload_folder = Path(app.root_path).parent / upload_folder
    upload_folder.mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = str(upload_folder)

    db.init_app(app)
    Migrate(app, db, compare_type=True)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"
    login_manager.user_loader(load_user)

    register_jinja_helpers(app)
    _register_context_processors(app)
    _register_routes(app)
    _register_error_handlers(app)

    # `db.create_all()` is a development convenience: it only creates missing
    # tables and seeds the default configuration rows. Schema changes are done
    # with Alembic (Flask-Migrate) — set SKIP_DB_INIT=1 when running
    # `flask db migrate/upgrade` so the schema stays owned by the migration.
    if os.environ.get("SKIP_DB_INIT") != "1":
        with app.app_context():
            db.create_all()
            ensure_default_config()

    return app


def _register_context_processors(app):
    from app.services.chat import unread_count

    @app.context_processor
    def inject_globals():
        from flask import current_app, g

        user = None
        try:
            from flask_login import current_user

            user = current_user
        except Exception:  # pragma: no cover
            user = None
        unread = 0
        try:
            if user is not None and getattr(user, "is_authenticated", False):
                unread = unread_count(user)
        except Exception:  # pragma: no cover
            unread = 0
        return {
            "site_name": "KMITL Rent",
            "current_user_unread": unread,
            "allowed_email_domain": current_app.config.get(
                "ALLOWED_EMAIL_DOMAIN", C.ALLOWED_EMAIL_DOMAIN
            ),
        }


def _register_routes(app):
    from app.routes.advertising import blueprint as advertising_bp
    from app.routes.auth import blueprint as auth_bp
    from app.routes.borrower import blueprint as borrower_bp
    from app.routes.chat import blueprint as chat_bp
    from app.routes.dashboard import blueprint as dashboard_bp
    from app.routes.lender import blueprint as lender_bp
    from app.routes.marketplace import blueprint as marketplace_bp
    from app.routes.profile import blueprint as profile_bp
    from app.routes.rentals import blueprint as rentals_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(marketplace_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(borrower_bp, url_prefix="/borrower")
    app.register_blueprint(lender_bp, url_prefix="/lender")
    app.register_blueprint(rentals_bp)
    app.register_blueprint(advertising_bp, url_prefix="/lender/advertising")
    app.register_blueprint(chat_bp, url_prefix="/chat")
    app.register_blueprint(profile_bp)

    upload_folder = app.config["UPLOAD_FOLDER"]

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        # send_from_directory prevents path traversal outside UPLOAD_FOLDER
        return send_from_directory(upload_folder, filename)


def _register_error_handlers(app):
    @app.errorhandler(400)
    def bad_request(error):
        return render_template("errors/400.html", error=error), 400

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/403.html", error=error), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html", error=error), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template("errors/500.html", error=error), 500
