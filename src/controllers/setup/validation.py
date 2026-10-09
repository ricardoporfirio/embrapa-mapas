import math
from datetime import date
from matplotlib import colormaps
from src.controllers.setup import VALID_TYPES


def integer(value, label):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{label} deve ser um inteiro.")
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ValueError(f"{label} deve ser um inteiro.") from None


def validate_payload(payload, culture):
    if not isinstance(payload, dict):
        raise ValueError("Envie um objeto JSON.")
    payload = payload.copy()
    if payload.get("culture", culture) != culture:
        raise ValueError("A cultura informada deve corresponder à URL.")
    payload["culture"] = culture
    if payload.get("type") not in VALID_TYPES:
        raise ValueError("Tipo inválido.")
    years = payload.get("years")
    if not isinstance(years, list) or not 1 <= len(years) <= 30:
        raise ValueError("Selecione entre 1 e 30 anos.")
    years = sorted({integer(year, "Ano") for year in years})
    if any(year < 1974 or year > date.today().year for year in years):
        raise ValueError("Ano fora do intervalo permitido.")
    payload["years"] = years
    shape = integer(payload.get("shapes_year"), "Ano das geometrias")
    if not 1872 <= shape <= date.today().year:
        raise ValueError("Ano das geometrias inválido.")
    payload["shapes_year"] = shape
    if not isinstance(payload.get("colormap"), str) or payload["colormap"] not in colormaps:
        raise ValueError("Paleta de cores inválida.")
    bins = validate_bins(payload.get("bins"), culture, payload["type"])
    payload["bins"] = bins
    payload.setdefault("basemap", "none")
    if payload["basemap"] not in {"none", "osm"}:
        raise ValueError("Fundo de mapa inválido.")
    for key, default in (("stream", True), ("fixed_bins", True)):
        payload.setdefault(key, default)
        if not isinstance(payload[key], bool):
            raise ValueError(f"{key} deve ser verdadeiro ou falso.")
    return payload


def validate_bins(bins, culture, indicator):
    if not isinstance(bins, dict) or bins.get("mode") not in {"automatic", "equal_width", "manual", "cileite"}:
        raise ValueError("Configuração de intervalos inválida.")
    bins = bins.copy()
    if bins["mode"] == "cileite":
        if culture != "cow":
            raise ValueError("Os presets Cileite são exclusivos para bovinos.")
        bins = {"mode": "cileite", "indicator": indicator}
    if bins["mode"] == "equal_width":
        bins["k"] = integer(bins.get("k"), "Número de classes")
        if not 2 <= bins["k"] <= 12:
            raise ValueError("Use entre 2 e 12 classes.")
        bins = {"mode": "equal_width", "k": bins["k"]}
    if bins["mode"] == "manual":
        try:
            values = [float(x.strip()) for x in str(bins.get("breaks", "")).split(",")]
        except ValueError:
            raise ValueError("Informe limites numéricos separados por vírgula.") from None
        if not 1 <= len(values) <= 11 or any(not math.isfinite(x) for x in values) or any(a >= b for a,b in zip(values, values[1:])):
            raise ValueError("Informe de 1 a 11 limites finitos em ordem crescente, sem repetição.")
        bins = {"mode": "manual", "breaks": ", ".join(str(value) for value in values)}
    if bins["mode"] == "automatic":
        bins = {"mode": "automatic"}
    return bins
