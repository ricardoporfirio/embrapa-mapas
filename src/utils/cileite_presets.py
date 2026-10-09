"""Classes publicadas pelo Cileite, com referência por indicador, UF e ano."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def catalog():
    return json.loads(Path(__file__).with_name("cileite_bins.json").read_text(encoding="utf-8"))


def preset_entry(indicator, year, territory="brasil"):
    entries = catalog()["presets"]
    matches = [p for p in entries if p["indicator"] == indicator and p["territory"] == territory.lower()]
    if not matches:
        matches = [p for p in entries if p["indicator"] == indicator and p["territory"] == "brasil"]
    if not matches:
        raise ValueError("Indicador sem preset Cileite.")
    previous = [p for p in matches if p["year"] <= int(year)]
    return max(previous, key=lambda p: p["year"]) if previous else min(matches, key=lambda p: p["year"])


def preset_limits(indicator, year, territory="brasil"):
    return preset_entry(indicator, year, territory)["breaks"] + [float("inf")]
