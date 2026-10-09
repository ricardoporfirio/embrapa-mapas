# src/blueprints/setup.py
from flask import Blueprint, render_template, abort
from src.utils.get_available_years import AvailableYears
from src.core.sidra.enums import Culture

bp_setup = Blueprint("setup", __name__, url_prefix="/setup")

# Domínios aceitos
VALID_CULTURES = {"cow", "goat", "sheep"}
VALID_TYPES = {
    "milking": {"label": "Ordenha"},
    "production": {"label": "Produção"},
    "milking-density": {"label": "Densidade de ordenha"},
    "production-density": {"label": "Densidade de produção"},
    "productivity": {"label": "Produtividade"},
}


@bp_setup.route("/", methods=["GET"])
def index():
    # Página inicial do Setup (pode ser um hub com links)
    return render_template("setup/index.html")


# Front Controller — uma página para qualquer culture e (opcionalmente) um tipo
@bp_setup.route("/<culture>/", defaults={"rtype": None}, methods=["GET"])
@bp_setup.route("/<culture>/<rtype>/", methods=["GET"])
def front(culture, rtype):
    if culture not in VALID_CULTURES:
        abort(404)
    if rtype is not None and rtype not in VALID_TYPES:
        abort(404)

    prefix = culture.upper()
    production = rtype in {"production", "production-density"}
    table = Culture[f"{prefix}_{'PRODUCTION' if production else 'MILKING'}"].value
    available_years = AvailableYears(table).get()
    ibge_available_years = available_years["ibge"]
    shapes_available_years = available_years["shapes"]
    if rtype == "productivity":
        production_years = AvailableYears(Culture[f"{prefix}_PRODUCTION"].value).get()["ibge"]
        ibge_available_years = sorted(set(ibge_available_years) & set(production_years))
    if not ibge_available_years or not shapes_available_years:
        abort(503, description="Não foi possível consultar os anos disponíveis. Tente novamente mais tarde.")

    ibge_last_year = max(ibge_available_years)
    shapes_last_year = max(shapes_available_years)

    return render_template(
        "setup/front.html",
        culture=culture,
        current_type=rtype,  # pode ser None
        valid_types=VALID_TYPES,  # para labels
        available_years=ibge_available_years,
        last_year=ibge_last_year,
        shapes_available_years=shapes_available_years,
        shapes_last_year=shapes_last_year,
    )


from src.controllers.setup import controller
from src.controllers.setup import presets
