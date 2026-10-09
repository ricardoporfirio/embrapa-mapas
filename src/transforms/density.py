"""Densidade por área geodésica, em km?."""
import numpy as np
import pandas as pd
from pyproj import Geod
from shapely.ops import orient


def transform_density(df, multiplier: float = 1.0):
    if "geometry" not in df.columns or df.crs is None:
        raise ValueError("A densidade requer geometrias com CRS definido.")
    geod = Geod(ellps="GRS80")
    geographic = df.to_crs(4674)
    def area(geometry):
        if geometry is None or geometry.is_empty:
            return np.nan
        return abs(geod.geometry_area_perimeter(orient(geometry, sign=1.0))[0]) / 1e6
    areas = geographic.geometry.map(area)
    result = df.copy()
    result["value"] = pd.to_numeric(df["value"], errors="coerce") * multiplier / areas.where(areas > 0)
    result["value"] = result["value"].replace([np.inf, -np.inf], np.nan)
    return result
