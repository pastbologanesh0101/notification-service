"""Application factory for the Notification Service.

Usage:

    from app import create_app
    app = create_app()               # production-ish: notifications.db file
    app = create_app(testing=True)    # tests: in-memory sqlite DB

A single sqlite3 connection is created per app instance and reused for the
lifetime of that app (see app/db.py for why). This is a deliberate
simplification suited to a small demo service, not a high-concurrency
production deployment.
"""

import os

from flask import Flask

from . import db as db_module

DEFAULT_DB_FILENAME = "notifications.db"


def create_app(testing=False, database=None, sleep_fn=None, max_retries=None, webhook_default_url=None):
    app = Flask(__name__)
    app.config["TESTING"] = bool(testing)

    if database is None:
        database = ":memory:" if testing else os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), DEFAULT_DB_FILENAME
        )
    app.config["DATABASE"] = database

    if sleep_fn is not None:
        app.config["SLEEP_FN"] = sleep_fn
    if max_retries is not None:
        app.config["MAX_RETRIES"] = max_retries
    if webhook_default_url is not None:
        app.config["WEBHOOK_DEFAULT_URL"] = webhook_default_url

    conn = db_module.connect(database)
    db_module.init_schema(conn)
    app.db_conn = conn

    from .routes import bp

    app.register_blueprint(bp)

    return app
