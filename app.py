import os
import secrets
from pathlib import Path
from datetime import timedelta

from flask import Flask, jsonify, redirect, request, send_from_directory, session, url_for
from flask_wtf.csrf import CSRFProtect, CSRFError
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
csrf = CSRFProtect()


def create_app(test_config=None):
    load_dotenv(ROOT / ".env")
    from src.utils.network import configure_geobr_network
    configure_geobr_network()
    app = Flask(__name__, static_folder="static", template_folder="templates")
    production = os.getenv("APP_ENV", "development") == "production"
    secret = os.getenv("SECRET_KEY")
    if production and not secret and not test_config:
        raise RuntimeError("Defina SECRET_KEY no ambiente de produção.")
    app.config.update(
        SECRET_KEY=secret or secrets.token_hex(32),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
        MAX_CONTENT_LENGTH=64 * 1024,
        WTF_CSRF_TIME_LIMIT=3600,
    )
    if test_config:
        app.config.update(test_config)
    csrf.init_app(app)

    from src.controllers.home import bp_home
    from src.controllers.auth import bp_auth
    from src.controllers.setup import bp_setup
    from src.controllers.sse import bp_sse
    app.register_blueprint(bp_home)
    app.register_blueprint(bp_auth, url_prefix="/auth")
    app.register_blueprint(bp_setup, url_prefix="/setup")
    app.register_blueprint(bp_sse)

    @app.before_request
    def protect_setup():
        if request.path.startswith("/setup") and not session.get("user"):
            if request.method != "GET" or request.path.startswith(("/setup/events/", "/setup/jobs/")):
                return jsonify(message="Faça login para acessar as configurações."), 401
            return redirect(url_for("home.login", reason="restricted"))

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return jsonify(message="Sessão do formulário expirada. Recarregue a página."), 400

    @app.after_request
    def response_headers(response):
        response.headers.pop("Connection", None)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.get("/mapas/<path:filename>")
    def serve_mapas(filename):
        return send_from_directory(ROOT / "mapas", filename)

    @app.get("/poster/<path:filename>")
    def serve_poster(filename):
        return send_from_directory(ROOT / "poster", filename)

    return app


app = create_app()

if __name__ == "__main__":
    from waitress import serve
    serve(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5001")))
