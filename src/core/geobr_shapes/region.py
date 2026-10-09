"""Downloader para todas as regiões do Brasil via geobr.read_region."""

from __future__ import annotations

import geopandas as gpd
from geobr import read_region

from .base_geo_downloader import BaseGeoDownloader


class RegionDownloader(BaseGeoDownloader):
    resource_name = "regions"

    def _fetch(self, *, year: int, simplified: bool) -> gpd.GeoDataFrame:
        year_capped = 2020 if year and year > 2020 else year
        return read_region(year=year_capped, simplified=simplified)

    def _postprocess(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        if "code_region" not in gdf.columns:
            raise KeyError(
                "Coluna 'code_region' não encontrada no retorno do geobr.read_region. "
                f"Cols disponíveis: {list(gdf.columns)}"
            )
        gdf = gdf.copy()
        gdf["code_region"] = gdf["code_region"].astype(int)

        gdf = gdf.rename(columns={"code_region": "geo_territory_code"})

        return gdf[["geo_territory_code", "geometry"]]
