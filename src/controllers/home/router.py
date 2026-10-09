from pathlib import Path
from src.utils.atomic import project_path
import glob
import os
import re

import numpy as np
import pandas as pd
from src.controllers.home import bp_home
from flask import jsonify, render_template, request


@bp_home.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@bp_home.route("/equipe", methods=["GET"])
def team():
    return render_template("team.html")


@bp_home.route("/login", methods=["GET"])
def login():
    return render_template("login.html")


@bp_home.route("/interactive_maps", methods=["GET"])
def interactive_maps():
    return render_template("interactive_maps.html", files=list_files())


@bp_home.route("/static_maps", methods=["GET"])
def static_maps():
    return render_template("static_maps.html", files=list_files("poster"))


@bp_home.route("/dashboard_cow", methods=["GET"])
def dashboard_cow():
    return render_template("dashboard_cow.html")


@bp_home.route("/dashboard_cow/", methods=["POST"])
def dashboard_cow_list():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(status="error", message="Envie um objeto JSON."), 400

    c_map = {"cow": "vacas", "sheep": "ovelhas", "goat": "cabras"}
    s_map = {
        "milking": "ordenha",
        "production": "producao",
        "milking_density": "densidade_ordenha",
        "production_density": "densidade_producao",
        "productivity": "produtividade",
    }

    if not isinstance(data.get("category"), str) or not isinstance(data.get("style"), str):
        return jsonify(status="error", message="category/style inválidos."), 400

    try:
        category_key = data["category"]
        style_key = data["style"]
        category = c_map[category_key]
        style = s_map[style_key]
    except KeyError:
        return jsonify({"status": "error", "message": "category/style inválidos."}), 400

    # níveis conforme regra: vaca => country/region/state ; senão => municipality
    levels = (
        ["country", "region", "state"] if category_key == "cow" else ["municipality"]
    )

    # regex p/ capturar ano no nome do arquivo
    year_regex = re.compile(r"(19|20)\d{2}")

    def load_concat(pattern: str, level: str) -> pd.DataFrame:
        """
        Lê todos os CSVs que batem no pattern, normaliza nomes de colunas e
        devolve DF com colunas: year, entity, value.
        """
        files = glob.glob(pattern)
        dfs = []

        for path in files:
            df = pd.read_csv(path)

            # normaliza nomes
            df.columns = [str(c).strip().lower() for c in df.columns]

            # extrai year do arquivo
            m = year_regex.search(Path(path).name)
            if not m:
                # tenta da coluna title (alguns títulos podem conter o ano)
                m = year_regex.search(" ".join(map(str, df.get("title", []))))
            if not m:
                # sem ano identificável, descarta este arquivo
                continue
            year = int(m.group(0))

            # value
            if "value" not in df.columns:
                # tenta localizar uma coluna numérica parecida
                candidates = [c for c in df.columns if c.startswith(("value", "valor"))]
                if not candidates:
                    continue
                df = df.rename(columns={candidates[0]: "value"})

            # entity name (usamos 'territory' para nomes)
            if "territory" not in df.columns:
                # sem territory, não conseguimos nomear
                continue

            # rótulo: para estado, se houver abbrev_state, prefixa "UF – Nome"
            if level == "state" and "abbrev_state" in df.columns:
                df["entity"] = df.apply(
                    lambda r: (
                        f"{str(r['abbrev_state']).strip()} – {str(r['territory']).strip()}"
                        if pd.notna(r.get("abbrev_state"))
                        else str(r["territory"]).strip()
                    ),
                    axis=1,
                )
            else:
                df["entity"] = df["territory"].astype(str).str.strip()

            # keep only
            df = df[["entity", "value"]].copy()
            df.insert(0, "year", year)

            dfs.append(df)

        if not dfs:
            return pd.DataFrame(columns=["year", "entity", "value"])

        out = pd.concat(dfs, ignore_index=True)

        # agregação defensiva caso hajam linhas repetidas da mesma entidade/ano
        out = (
            out.groupby(["year", "entity"], dropna=False)["value"]
            .sum(min_count=1)  # se tudo NaN, continua NaN
            .reset_index()
        )

        # NaN -> None p/ JSON
        out = out.replace({np.nan: None})
        return out

    payload_levels = {}

    for level in levels:
        pattern = str(project_path(f"dataframes/{category}/{style}/{level}/*.csv"))
        df = load_concat(pattern, level)

        if df.empty:
            payload_levels[level] = []
            continue

        # entidades estáveis (ordem alfabética)
        entities = (
            df["entity"].dropna().astype(str).drop_duplicates().sort_values().tolist()
        )

        # monta por ano arrays alinhados à 'entities'
        items = []
        for year, g in df.groupby("year", dropna=False):
            mvals = {str(r["entity"]): r["value"] for _, r in g.iterrows()}
            values = [mvals.get(e, None) for e in entities]
            items.append(
                {
                    "year": int(year),
                    "values": values,
                    "entities": entities,  # nomes (estado/região/município/país)
                }
            )

        items.sort(key=lambda it: it["year"])
        payload_levels[level] = items

    return jsonify(
        {
            "status": "ok",
            "category": category_key,
            "style": style_key,
            "levels": payload_levels,
        }
    )


def list_files(base_path="mapas"):
    structure = {}
    base = project_path(base_path)
    suffixes = {".html"} if base_path == "mapas" else {".png", ".jpg", ".jpeg"}
    for file in sorted(base.glob("*/*/*/*")):
        if not file.is_file() or file.suffix.lower() not in suffixes or file.name.startswith(".tmp-"):
            continue
        category, subcategory, year, name = file.relative_to(base).parts
        structure.setdefault(category, {}).setdefault(subcategory, {}).setdefault(year, []).append(name)
    return structure
