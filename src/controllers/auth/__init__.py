from flask import Blueprint

bp_auth = Blueprint("auth",__name__,url_prefix="/auth")

from src.controllers.auth import router