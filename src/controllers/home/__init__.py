from flask import Blueprint

bp_home = Blueprint("home",__name__,url_prefix="/")

from src.controllers.home import router