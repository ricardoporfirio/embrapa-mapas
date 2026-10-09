# src/transforms/productivity.py
"""Transformação de produtividade (produção / ordenha).

Calcula a razão entre produção e ordenha, com multiplicador.
Preserva `geometry` quando presente.
"""

from __future__ import annotations
import pandas as pd
import geopandas as gpd
from typing import List


def _common_keys(df1: pd.DataFrame, df2: pd.DataFrame) -> List[str]:
    """Determina chaves comuns para merge (sempre inclui `territory_code`)."""
    keys: List[str] = ["territory_code"]
    if "period" in df1.columns and "period" in df2.columns:
        keys.append("period")
    return keys


def transform_productivity(
    df_milking: pd.DataFrame,
    df_production: pd.DataFrame,
    *,
    multiplier: float = 1.0,
) -> pd.DataFrame | gpd.GeoDataFrame:
    """Calcula produtividade = (produção * multiplicador) / ordenhadas.

    Se ordenhadas == 0 ou houver dados ausentes, preserva aus?ncia de informa??o.

    Parameters
    ----------
    df_milking : pandas.DataFrame
        DataFrame com colunas: `territory_code`, `territory`, `value`.
        Pode conter `geometry`.
    df_production : pandas.DataFrame
        DataFrame com colunas: `territory_code`, `territory`, `value`.
        Pode conter `geometry`.
    multiplier : float, default=1.0
        Fator multiplicador aplicado à produção.

    Returns
    -------
    pandas.DataFrame or geopandas.GeoDataFrame
        DataFrame com colunas:
        - `territory_code`
        - `territory`
        - `period` (se existir)
        - `value` (produtividade)
        - `geometry` (se existir nos DFs de entrada)
    """
    milk = df_milking.copy()
    prod = df_production.copy()

    milk["value"] = pd.to_numeric(milk["value"], errors="coerce")
    prod["value"] = pd.to_numeric(prod["value"], errors="coerce")

    geometry_source = prod if "geometry" in prod.columns else milk
    geometry_crs = getattr(geometry_source, "crs", None)
    keys = _common_keys(milk, prod)

    merged = prod.merge(
        milk,
        on=keys,
        suffixes=("_prod", "_milk"),
        how="inner",
        validate="1:1",
    )

    # Divisão por zero e ausência de dados permanecem sem informação.
    ordenhadas = merged["value_milk"]
    producao = merged["value_prod"] * multiplier
    produtividade = producao / ordenhadas.where(ordenhadas > 0)

    result = pd.DataFrame(index=merged.index)
    result["territory_code"] = merged["territory_code"].astype(int)
    if "period" in merged.columns:
        result["period"] = merged["period"]

    if "territory_prod" in merged.columns:
        result["territory"] = merged["territory_prod"]
    elif "territory" in prod.columns:
        result["territory"] = prod["territory"]
    else:
        result["territory"] = merged.get("territory_milk", None)

    result["value"] = produtividade

    # A geometria acompanha as chaves usadas no merge.
    geometry_col = next((c for c in ("geometry_prod", "geometry", "geometry_milk") if c in merged.columns), None)
    if geometry_col:
        result = gpd.GeoDataFrame(result, geometry=merged[geometry_col], crs=geometry_crs)

    return result
