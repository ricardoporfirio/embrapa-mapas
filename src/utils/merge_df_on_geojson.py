# src/utils/merge_df_on_geojson.py
from __future__ import annotations

from typing import Optional
import pandas as pd
import geopandas as gpd


class GeoMerger:
    """Une DataFrame tabular a GeoDataFrame por código territorial.

    Parâmetros:
    - left_code_col: nome da coluna de código no DF (default: 'territory_code')
    - right_code_col: nome da coluna de código no GDF; por padrão usa 'geo_territory_code'
                      (se ausente, tenta inferir a partir de colunas legadas e cria um alias)
    - how: tipo de junção (default: 'left')
    - ensure_int: se True, força colunas de código para int (default: True)
    - drop_geo_code_duplicate: se True, remove colunas legadas após o merge (default: True)
    """

    def __init__(
        self,
        *,
        left_code_col: str = "territory_code",
        right_code_col: Optional[str] = None,  # se None, usa 'geo_territory_code'
        how: str = "left",
        ensure_int: bool = True,
        drop_geo_code_duplicate: bool = True,
    ) -> None:
        self.left_code_col = left_code_col
        self.right_code_col = right_code_col or "geo_territory_code"
        self.how = how
        self.ensure_int = ensure_int
        self.drop_geo_code_duplicate = drop_geo_code_duplicate

    def merge(self, df: pd.DataFrame, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Executa o merge e retorna um GeoDataFrame pronto para plot."""

        if "geometry" not in gdf.columns:
            raise ValueError("GeoDataFrame não possui coluna 'geometry'.")

        if self.left_code_col not in df.columns:
            raise ValueError(
                f"Coluna de código do DF não encontrada: '{self.left_code_col}'."
            )

        # Cópias defensivas
        df_left = df.copy()
        gdf_right = gdf.copy()

        right_col = self.right_code_col
        legacy_cols = ("code_muni", "code_state", "code_region")
        created_alias = False
        legacy_found: Optional[str] = None

        # Se o GDF não tiver geo_territory_code, tentar inferir de colunas legadas e criar alias
        if right_col not in gdf_right.columns:
            for cand in legacy_cols:
                if cand in gdf_right.columns:
                    gdf_right[right_col] = gdf_right[cand]
                    created_alias = True
                    legacy_found = cand
                    break
            if not created_alias:
                raise ValueError(
                    "GeoDataFrame não possui 'geo_territory_code' e nenhuma coluna legada "
                    f"foi encontrada ({', '.join(legacy_cols)})."
                )

        # Normalizar tipos para inteiro, se solicitado
        if self.ensure_int:
            try:
                df_left[self.left_code_col] = (
                    pd.to_numeric(df_left[self.left_code_col], errors="raise")
                    .astype("Int64")
                    .astype(int)
                )
            except Exception as e:
                raise ValueError(
                    f"Falha ao converter DF['{self.left_code_col}'] para inteiro: {e}"
                ) from e

            try:
                gdf_right[right_col] = (
                    pd.to_numeric(gdf_right[right_col], errors="raise")
                    .astype("Int64")
                    .astype(int)
                )
            except Exception as e:
                raise ValueError(
                    f"Falha ao converter GDF['{right_col}'] para inteiro: {e}"
                ) from e

        # Merge preservando as geometrias do GDF
        merged = gdf_right.merge(
            df_left,
            how=self.how,
            left_on=right_col,
            right_on=self.left_code_col,
            validate="m:1",  # cada geometria casa com no máx. 1 linha do DF
        )

        # Limpeza de colunas legadas e duplicatas
        cols_to_drop = []
        if self.drop_geo_code_duplicate:
            # se criamos alias a partir de uma coluna legada, remova a legada
            if created_alias and legacy_found and legacy_found in merged.columns:
                cols_to_drop.append(legacy_found)
            # evitar manter ambas se nomes diferem
            if right_col != self.left_code_col and right_col in merged.columns:
                # mantemos apenas left_code_col como referência tabular
                cols_to_drop.append(right_col)

        if cols_to_drop:
            merged = merged.drop(columns=list(dict.fromkeys(cols_to_drop)))  # unique

        # Garantir GeoDataFrame com CRS preservado
        return gpd.GeoDataFrame(merged, geometry="geometry", crs=gdf.crs)

    # ---------------------- helpers (mantidos para compatibilidade) ----------------------
    @staticmethod
    def _infer_right_code_col(gdf: gpd.GeoDataFrame) -> Optional[str]:
        # Mantido apenas se algum código externo depender; preferir sempre 'geo_territory_code'
        return "geo_territory_code" if "geo_territory_code" in gdf.columns else None
