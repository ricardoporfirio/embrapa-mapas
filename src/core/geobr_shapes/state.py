"""Downloader para todas as UFs do Brasil via geobr.read_state, colunas padronizadas.

- CRS: EPSG:4326
- Colunas de saída:
    - state_code   (int)
    - state_name   (str)
    - state_abbrev (str, se disponível)
    - geometry
"""

from __future__ import annotations

from typing import List
import geopandas as gpd
from geobr import read_state

from .base_geo_downloader import BaseGeoDownloader


def _first_present(cols: List[str], gdf: gpd.GeoDataFrame) -> str | None:
    for c in cols:
        if c in gdf.columns:
            return c
    return None


class StateDownloader(BaseGeoDownloader):
    resource_name = "states"

    def _fetch(self, *, year: int, simplified: bool) -> gpd.GeoDataFrame:
        year_capped = 2020 if year and year > 2020 else year
        return read_state(year=year_capped, simplified=simplified)

    def _postprocess(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        gdf = gdf.copy()

        code_col = _first_present(["code_state", "code", "code_meso", "code_uf"], gdf)
        name_col = _first_present(["name_state", "name", "nome", "state"], gdf)
        abbr_col = _first_present(
            ["abbrev_state", "state_abbrev", "abrev_state", "sigla", "uf"], gdf
        )

        if code_col is None or name_col is None:
            raise KeyError(
                "Não encontrei colunas de código e/ou nome do estado no retorno do geobr.read_state. "
                f"Cols disponíveis: {list(gdf.columns)}"
            )

        rename_map = {code_col: "state_code", name_col: "state_name"}
        if abbr_col:
            rename_map[abbr_col] = "state_abbrev"

        gdf = gdf.rename(columns=rename_map)

        keep = ["state_code", "state_name", "geometry"]
        if "state_abbrev" in gdf.columns:
            keep.insert(2, "state_abbrev")
        gdf = gdf[keep]

        # tipos e limpeza
        try:
            gdf["state_code"] = gdf["state_code"].astype(int)
        except Exception:
            pass

        gdf = gdf.drop_duplicates(
            subset=[c for c in gdf.columns if c != "geometry"]
        ).reset_index(drop=True)

        # tentar corrigir geometrias inválidas sem explodir
        try:
            invalid = ~gdf.is_valid
            if invalid.any():
                gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].buffer(0)
        except Exception:
            pass

        sort_col = "state_abbrev" if "state_abbrev" in gdf.columns else "state_name"
        gdf = gdf.sort_values(by=sort_col, kind="stable").reset_index(drop=True)

        gdf = gdf.rename(columns={"state_code": "geo_territory_code"})
        return gdf
