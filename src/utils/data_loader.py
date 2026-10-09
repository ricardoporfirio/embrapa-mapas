from pathlib import Path
import pandas as pd
import re
from cachetools import TTLCache

DATA_DIR = Path(__file__).resolve().parents[2] / "dataframes"
VALID_SUBJECT = "vacas"
VALID_METRICS = {
    "producao",
    "ordenha",
    "produtividade",
    "densidade_producao",
    "densidade_ordenha",
}
VALID_LEVELS = {"country", "region", "state", "municipality"}

_df_cache = TTLCache(maxsize=64, ttl=600)
_year_re = re.compile(r"-(\d{4})\.csv$", re.IGNORECASE)


def _safe_int(x):
    try:
        return int(x)
    except Exception:
        return None


def load_series(subject: str, metric: str, level: str) -> pd.DataFrame:
    if subject != VALID_SUBJECT:
        raise ValueError("A versão atual só suporta 'vacas'.")
    if metric not in VALID_METRICS:
        raise ValueError(f"Métrica inválida: {metric}")
    if level not in VALID_LEVELS:
        raise ValueError(f"Nível inválido: {level}")

    cache_key = (subject, metric, level)
    if cache_key in _df_cache:
        return _df_cache[cache_key].copy()

    folder = DATA_DIR / subject / metric / level
    if not folder.exists():
        raise FileNotFoundError(f"Pasta não encontrada: {folder}")

    frames = []
    for csv_path in sorted(folder.glob("*.csv")):
        m = _year_re.search(csv_path.name)
        if not m:
            continue
        year = int(m.group(1))
        df = pd.read_csv(csv_path)

        expected = [
            "country_name",
            "country_abbrev",
            "territory_code",
            "territory",
            "value",
            "title",
            "unit",
        ]
        missing = [c for c in expected if c not in df.columns]
        if missing:
            raise ValueError(f"Colunas faltando em {csv_path.name}: {missing}")

        use = df[["territory_code", "territory", "value", "title", "unit"]].copy()
        use["year"] = year
        use["territory_code"] = use["territory_code"].apply(_safe_int)
        use["value"] = pd.to_numeric(use["value"], errors="coerce")
        frames.append(use)

    if not frames:
        raise ValueError(f"Sem CSVs válidos em {folder}")

    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=["year", "value", "territory_code"])
    out["year"] = out["year"].astype(int)
    out["territory_code"] = out["territory_code"].astype(int)
    out = out.sort_values(["territory_code", "year"]).reset_index(drop=True)

    _df_cache[cache_key] = out.copy()
    return out
