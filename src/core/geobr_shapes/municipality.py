"""Downloader para todos os municípios do Brasil via geobr.read_municipality."""

from __future__ import annotations

import geopandas as gpd
from geobr import read_municipality

from .base_geo_downloader import BaseGeoDownloader


class MunicipalityDownloader(BaseGeoDownloader):
    resource_name = "municipalities"

    def _fetch(self, *, year: int, simplified: bool) -> gpd.GeoDataFrame:
        return read_municipality(year=year, simplified=simplified)

    def _postprocess(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        # garante tipos e colunas essenciais
        if "code_muni" not in gdf.columns or "abbrev_state" not in gdf.columns:
            raise KeyError(
                "Colunas esperadas ausentes no retorno do geobr.read_municipality: "
                f"encontrei {list(gdf.columns)}"
            )
        gdf = gdf.copy()
        gdf["code_muni"] = gdf["code_muni"].astype(int)
        gdf = gdf.rename(columns={"code_muni": "geo_territory_code"})

        return gdf[["geo_territory_code", "abbrev_state", "geometry"]]
