"""Flask application factory for the ZORA API."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from flask import Flask
from flask_cors import CORS

from zora.api import routes

_STATIC_DIR = str(Path(__file__).parent.parent.parent / "static")


def create_app(config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, static_folder=_STATIC_DIR, static_url_path="/static")

    origins = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
    CORS(app, origins=origins)

    app.register_blueprint(routes.bp)

    @app.get("/")
    def index() -> Any:
        return app.send_static_file("index.html")

    if config:
        app.config.update(config)

    return app
