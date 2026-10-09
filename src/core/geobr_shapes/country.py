"""
Downloader para o contorno do Brasil via geobr.read_country, com fallback quando o provedor
retorna apenas 'geometry'.

- CRS: EPSG:4326
- Colunas de saída:
    - country_code   (int; fallback=76)
    - country_name   (str; fallback='Brasil')
    - country_abbrev (str; fallback='BR')
    - geometry

Obs.: se year > 2020, usa-se year=2020.
"""

from __future__ import annotations

from typing import List
import geopandas as gpd
from geobr import read_country

from .base_geo_downloader import BaseGeoDownloader


def _first_present(cols: List[str], gdf: gpd.GeoDataFrame) -> str | None:
    for c in cols:
        if c in gdf.columns:
            return c
    return None


class CountryDownloader(BaseGeoDownloader):
    resource_name = "country"

    def _fetch(self, *, year: int, simplified: bool = True) -> gpd.GeoDataFrame:
        year_capped = 2020 if year and year > 2020 else year
        return read_country(year=year_capped, simplified=simplified)

    def _postprocess(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        gdf = gdf.copy()

        code_col = _first_present(["code_country", "code", "code_br", "codigo"], gdf)
        name_col = _first_present(["name_country", "name", "nome", "country"], gdf)
        abbr_col = _first_present(
            ["abbrev_country", "country_abbrev", "abrev_country", "sigla", "abbr"], gdf
        )

        # --- nome ---
        if name_col:
            gdf = gdf.rename(columns={name_col: "country_name"})
        else:
            # fallback quando só vem geometry
            gdf["country_name"] = "Brasil"

        # --- código ---
        if code_col:
            gdf = gdf.rename(columns={code_col: "country_code"})
            try:
                gdf["country_code"] = gdf["country_code"].astype(int)
            except Exception:
                pass
        else:
            gdf["country_code"] = 76  # ISO numérico do Brasil

        # --- sigla ---
        if abbr_col:
            gdf = gdf.rename(columns={abbr_col: "country_abbrev"})
        else:
            gdf["country_abbrev"] = "BR"

        # manter apenas colunas finais
        gdf = gdf[["country_code", "country_name", "country_abbrev", "geometry"]]

        # limpeza básica
        gdf = gdf.drop_duplicates(
            subset=["country_code", "country_name", "country_abbrev"]
        ).reset_index(drop=True)

        # corrigir geometrias inválidas, se houver
        try:
            invalid = ~gdf.is_valid
            if invalid.any():
                gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].buffer(0)
        except Exception:
            pass

        gdf = gdf.sort_values(by="country_name", kind="stable").reset_index(drop=True)

        gdf = gdf.rename(columns={"country_code": "geo_territory_code"})
        gdf["geo_territory_code"] = gdf["geo_territory_code"].astype(int)

        return gdf[["geo_territory_code", "country_name", "country_abbrev", "geometry"]]
