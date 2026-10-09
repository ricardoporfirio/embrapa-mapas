# src/utils/make_map_dynamic.py
"""Geração de mapas dinâmicos com Folium (mesma lógica, usando novas classes)."""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache
from typing import Iterable, List, Sequence, Any, Optional

from src.utils.atomic import atomic_output
import folium
from folium.map import CustomPane
import geopandas as gpd
import numpy as np
import pandas as pd
from geobr import read_country
from shapely.geometry import box
from shapely.ops import unary_union

# utilitários
from src.core.geobr_shapes import StateDownloader, RegionDownloader
from src.utils.define_colors import ColorPalette

import io
import re
from contextlib import redirect_stdout
import unicodedata


# ----------------------------- helpers básicos ---------------------------------
from src.utils.classification import format_number as _pt_number, labels_from_bins as _labels_from_bins


def _color_for_value(val: float, bins: Sequence[float], palette: Sequence[str]) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "#cccccc"
    for i, b in enumerate(bins):
        if val <= b:
            return palette[i]
    return palette[-1]


def _legend_html(
    title: str, subtitle: str, year: int, bins: Sequence[float], colors: Sequence[str]
) -> str:
    labels = _labels_from_bins(bins)
    items = "\n".join(
        f"""<div style="display:flex; align-items:center; margin:2px 0;">
<span style="display:inline-block;width:18px;height:12px;background:{colors[i]};border:1px solid #333;margin-right:8px"></span>
<span style="font-size:12px;color:#111">{labels[i]}</span></div>"""
        for i in range(len(labels))
    )
    return f"""<div id="custom-legend" style="position:absolute; z-index:9999; background:white; padding:10px 12px; border-radius:6px; border:1px solid #bbb; box-shadow:0 1px 4px rgba(0,0,0,.2); bottom: 12px; right: 12px; font-family:Arial, sans-serif;">
<div style="font-weight:700; font-size:16px; color:#111; margin-bottom:2px;">{title}</div>
<div style="font-size:12px; color:#555; margin-bottom:6px;">{subtitle}</div>
<div style="font-size:12px; color:#111; margin-bottom:6px;"><strong>Ano:</strong> {year}</div>
{items}
<div style="font-size:12px"><span style="display:inline-block;width:18px;height:12px;background:#ccc;border:1px solid #333;margin-right:8px"></span>Sem informação</div>
</div>"""


# ----------------------------- helpers geográficos ---------------------------------
@lru_cache(maxsize=1)
def _brazil_mask_geojson() -> gpd.GeoDataFrame:
    year = 2020
    try:
        br = read_country(year=2020, simplified=True).to_crs(4326)
    except Exception:
        buf = io.StringIO()
        with redirect_stdout(buf):
            geobr_list_ok = True
            try:
                from geobr import list_geobr

                list_geobr()
            except Exception:
                geobr_list_ok = False
        nearest = None
        if geobr_list_ok:
            text = buf.getvalue()
            m = re.search(
                r"Function:\s*read_country[\s\S]*?(?:Years available:|Years:)(.+?)\n",
                text,
                flags=re.IGNORECASE,
            )
            if m:
                years = sorted(
                    {
                        int(y)
                        for y in re.findall(
                            r"\b(18\d{2}|19\d{2}|20\d{2})\b", m.group(1)
                        )
                    }
                )
                if years:
                    nearest = min(years, key=lambda y: abs(y - year))
        retry_year = nearest if nearest is not None else 2020
        br = read_country(year=retry_year, simplified=True).to_crs(4326)

    br_union = unary_union(br.geometry)
    world = gpd.GeoDataFrame(geometry=[box(-180, -90, 180, 90)], crs=4326)
    mask_geom = world.geometry.iloc[0].difference(br_union)
    return gpd.GeoDataFrame(geometry=[mask_geom], crs=4326)


def _equal_bins_from_values(vals: pd.Series, n_classes: int) -> List[float]:
    vals = (
        pd.to_numeric(vals, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    )
    if vals.empty:
        return [0, float("inf")]
    vmin, vmax = float(vals.min()), float(vals.max())
    if vmin == vmax:
        return [vmax, float("inf")]
    edges = np.linspace(vmin, vmax, n_classes, endpoint=True)[1:]
    return [float(x) for x in edges] + [float("inf")]


def _guess_name_field(cols: Sequence[str]) -> str | None:
    cand = [
        "municipio",
        "município",
        "territory",
        "name",
        "nome",
        "municipality",
        "city",
    ]
    lower_map = {c.lower(): c for c in cols}
    for c in cand:
        if c in lower_map:
            return lower_map[c]
    return None


# ----------------------------- helpers de estado/UF ---------------------------------
def _guess_state_cols(cols: Sequence[str]) -> list[str]:
    return [
        c
        for c in [
            "abbrev_state",
            "state_abbrev",
            "abrev_state",
            "state_name",
            "name_state",
            "code_state",
            "state_code",
        ]
        if c in cols
    ]


def _norm_str(x: Any) -> str:
    s = str(x) if x is not None else ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.strip().lower()


def _mask_for_states(df: pd.DataFrame, targets: set[str]) -> pd.Series:
    poss = _guess_state_cols(df.columns)
    for extra in ("name_state", "state_name"):
        if extra in df.columns and extra not in poss:
            poss.append(extra)
    if not poss:
        return pd.Series(False, index=df.index)
    tgt_norm = {_norm_str(t) for t in targets}
    mask = pd.Series(False, index=df.index)
    for col in poss:
        vals = df[col].astype(str).map(_norm_str)
        mask |= vals.isin(tgt_norm)
    return mask


def _sanitize_props(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Converte NaN numérico -> None e NaN texto -> '' para exportar como GeoJSON."""
    out = df.copy()
    for c in cols:
        if c == "geometry":
            continue
        if pd.api.types.is_numeric_dtype(out[c]):
            out[c] = out[c].astype(object)
            out[c] = out[c].where(~pd.isna(out[c]), None)
        else:
            out[c] = out[c].astype(object)
            out[c] = out[c].where(out[c].notna(), "")
    return out


# -------------------------------- classe principal ---------------------------------
class DynamicMap:
    """
    Mesma lógica do estático, mas em Folium. Quando state=GO, aplica lógica "Centro-Oeste":
    **GO + DF** entram juntos nos dados e no traçado.
    """

    def __init__(
        self,
        *,
        year: int = 2022,
        bins: int | Sequence[float] = 5,
        color_code: str = "YlOrRd",
        center: tuple[float, float] = (-14.2350, -51.9253),
        zoom_start: int = 4,
        tiles: str | None = None,
        show_legend: bool = True,
        remove_outside_brazil: bool = True,
        scope: str = "brasil",
        show_state_outline: bool = True,
        show_region_outline: bool = True,
        state_filter: Any | None = None,
        region: str | None = None,
        state: str | int | None = None,
        tooltip_fields: Optional[Iterable[str]] = ("territory", "value", "unit"),
        output_html: str | Path | None = None,
    ) -> None:
        self.year = year
        self.bins = bins
        self.color_code = color_code
        self.center = center
        self.zoom_start = zoom_start
        self.tiles = tiles
        self.show_legend = show_legend
        self.remove_outside_brazil = remove_outside_brazil
        self.scope = scope
        self.show_state_outline = show_state_outline
        self.show_region_outline = show_region_outline
        self.state_filter = state_filter
        self.region = region
        self.state = state
        self.tooltip_fields = list(tooltip_fields) if tooltip_fields else None
        self.output_html = Path(output_html) if output_html is not None else None

        self._palette = ColorPalette(self.color_code)
        self._state_dl = StateDownloader()
        self._region_dl = RegionDownloader()

    def build(self, gdf: gpd.GeoDataFrame) -> folium.Map:
        if self.region and self.state:
            raise ValueError("Use apenas um de 'region' ou 'state', não ambos.")

        # -------------------------------- region --------------------------------
        scope = self.scope
        region_to_states = {
            "norte": ["AC", "AP", "AM", "PA", "RO", "RR", "TO"],
            "nordeste": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
            "centro-oeste": ["DF", "GO", "MT", "MS"],
            "sudeste": ["ES", "MG", "RJ", "SP"],
            "sul": ["PR", "RS", "SC"],
        }
        gdf_work = gdf
        if self.region:
            reg_key = self.region.strip().lower()
            if reg_key not in region_to_states:
                raise ValueError(
                    f"Região '{self.region}' inválida. Opções: {list(region_to_states.keys())}"
                )
            possible_cols = [
                c
                for c in ["abbrev_state", "state_abbrev", "abrev_state"]
                if c in gdf_work.columns
            ]
            if not possible_cols:
                raise KeyError(
                    "Para usar 'region', o gdf precisa ter uma coluna de sigla de estado."
                )
            gdf_work = gdf_work[
                gdf_work[possible_cols[0]].isin(region_to_states[reg_key])
            ].copy()
            scope = "regiao"

        # -------------------------------- state (LÓGICA CENTRO-OESTE p/ GO) --------------------------------
        state_filter = self.state_filter
        if self.state:
            key_norm = _norm_str(self.state)
            possible_cols = [
                c
                for c in [
                    "abbrev_state",
                    "state_abbrev",
                    "abrev_state",
                    "state_name",
                    "name_state",
                    "code_state",
                    "state_code",
                ]
                if c in gdf_work.columns
            ]
            if not possible_cols:
                raise KeyError(
                    "Para usar 'state', o gdf precisa ter coluna de UF, nome ou código do estado."
                )

            # targets por coluna quando o estado pedido é GO (GO + DF)
            go_targets_by_col = {
                "abbrev_state": {"go", "df"},
                "state_abbrev": {"go", "df"},
                "abrev_state": {"go", "df"},
                "state_name": {"goias", "distrito federal"},
                "name_state": {"goias", "distrito federal"},
                "code_state": {"52", "53", "5200000", "5300000"},
                "state_code": {"52", "53", "5200000", "5300000"},
            }

            mask = pd.Series(False, index=gdf_work.index)
            for col in possible_cols:
                vals = gdf_work[col].astype(str).map(_norm_str)
                if key_norm in {"go", "goias", "goiás", "52", "5200000"}:
                    targets = go_targets_by_col.get(col, {key_norm})
                else:
                    targets = {key_norm}
                mask |= vals.isin(targets)

            gdf_work = gdf_work[mask].copy()
            scope = "estado"
            state_filter = self.state

            # opcional: se DF não está nos dados, injeta placeholder neutro (value=None)
            if key_norm in {"go", "goias", "goiás", "52", "5200000"}:
                has_df = False
                for col in possible_cols:
                    vals = gdf_work[col].astype(str).map(_norm_str)
                    if col in {"abbrev_state", "state_abbrev", "abrev_state"}:
                        has_df |= vals.eq("df").any()
                    elif col in {"state_name", "name_state"}:
                        has_df |= vals.eq("distrito federal").any()
                    elif col in {"code_state", "state_code"}:
                        has_df |= vals.isin({"53", "5300000"}).any()
                if not has_df:
                    year_states = 2020 if self.year > 2000 else self.year
                    states_inj = self._state_dl.download(
                        year=year_states, simplified=True
                    ).to_crs(4326)
                    mdf = _mask_for_states(
                        states_inj, {"df", "distrito federal", "53", "5300000"}
                    )
                    if mdf.any():
                        df_geom = states_inj.loc[mdf, "geometry"].values[0]
                        df_row = {
                            "geometry": df_geom,
                            "value": None,  # “sem dado” -> cinza. Troque por métrica se quiser.
                            "title": (
                                gdf_work.get("title", pd.Series(["Mapa"])).iloc[0]
                                if len(gdf_work)
                                else "Mapa"
                            ),
                            "unit": (
                                gdf_work.get("unit", pd.Series([""])).iloc[0]
                                if len(gdf_work)
                                else ""
                            ),
                            "abbrev_state": "DF",
                        }
                        gdf_work = pd.concat(
                            [
                                gdf_work,
                                gpd.GeoDataFrame(
                                    [df_row], geometry="geometry", crs=4326
                                ),
                            ],
                            ignore_index=True,
                        )

        # -------------------------------- validações & CRS --------------------------------
        if "geometry" not in gdf_work.columns:
            raise ValueError("gdf precisa conter coluna 'geometry'.")
        if "value" not in gdf_work.columns:
            raise ValueError("gdf precisa conter coluna 'value'.")
        gdf_work = gdf_work.to_crs(4326).copy()

        # -------------------------------- estados / regiões --------------------------------
        year_norm = 2020 if self.year > 2000 else self.year
        states = self._state_dl.download(year=year_norm, simplified=True).to_crs(4326)

        # -------------------------------- bins & paleta --------------------------------
        bins_list = (
            _equal_bins_from_values(gdf_work["value"], self.bins)
            if isinstance(self.bins, int)
            else list(self.bins)
        )
        if not np.isinf(bins_list[-1]):
            bins_list.append(float("inf"))
        try:
            colors = self._palette.generate(len(bins_list))
        except Exception:
            default_palette = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"]
            colors = (default_palette * ((len(bins_list) + 4) // 5))[: len(bins_list)]

        title = str(gdf_work.get("title", pd.Series(["Mapa"])).iloc[0])
        unit = str(gdf_work.get("unit", pd.Series([""])).iloc[0])
        subtitle = f"({unit})" if unit else ""

        # -------------------------------- mapa base & panes --------------------------------
        m = folium.Map(
            location=self.center,
            zoom_start=self.zoom_start,
            tiles=self.tiles,
            control_scale=True,
        )
        CustomPane("pane-mask", z_index=200).add_to(m)
        CustomPane("pane-dados", z_index=620).add_to(m)
        CustomPane("pane-contorno", z_index=650).add_to(m)
        folium.Map.get_root(m).html.add_child(
            folium.Element(
                """
<style>
.leaflet-pane.pane-contorno,
.leaflet-pane.pane-contorno * { pointer-events: none !important; }
</style>"""
            )
        )

        if self.remove_outside_brazil:
            mask_gdf = _brazil_mask_geojson()
            folium.GeoJson(
                mask_gdf,
                style_function=lambda feat: {
                    "fillColor": "#ffffff",
                    "color": "#ffffff",
                    "weight": 0,
                    "fillOpacity": 1.0,
                },
                pane="pane-mask",
                control=False,
            ).add_to(m)

        # -------------------------------- tooltips --------------------------------
        t_fields: List[str] = []
        if self.tooltip_fields:
            for f in self.tooltip_fields:
                if f in gdf_work.columns and f not in t_fields:
                    t_fields.append(f)
        if not t_fields:
            guess = _guess_name_field(list(gdf_work.columns))
            if guess:
                t_fields.append(guess)
            if "value" in gdf_work.columns:
                t_fields.append("value")
            if "unit" in gdf_work.columns:
                t_fields.append("unit")

        pt_alias_map = {
            "territory": "Município",
            "municipio": "Município",
            "município": "Município",
            "municipality": "Município",
            "city": "Município",
            "name": "Nome",
            "nome": "Nome",
            "value": "Valor",
            "unit": "Unidade",
            "abbrev_state": "UF",
            "state_abbrev": "UF",
            "state_name": "Estado",
            "name_state": "Estado",
            "code_state": "Código do Estado",
            "state_code": "Código do Estado",
        }

        if "value" in gdf_work.columns:
            gdf_work["__valor_fmt__"] = gdf_work["value"].apply(_pt_number)
            t_fields = ["__valor_fmt__" if f == "value" else f for f in t_fields]

        pt_aliases: List[str] = []
        for i, fcol in enumerate(t_fields):
            base_key = fcol.lower()
            base_label = pt_alias_map.get(base_key, fcol.capitalize())
            if i == 0 and base_label in {"Município", "Nome"}:
                pt_aliases.append(f"<b>{title}</b><br><b>{base_label}:</b>")
            elif fcol == "__valor_fmt__":
                pt_aliases.append("<b>Valor:</b>")
            else:
                pt_aliases.append(f"<b>{base_label}:</b>")

        def style_fn(feature):
            val = feature["properties"].get("value", None)
            return {
                "fillColor": _color_for_value(val, bins_list, colors),
                "color": "#333333",
                "weight": 0.3,
                "fillOpacity": (
                    0.9
                    if (
                        val is not None
                        and not (isinstance(val, float) and np.isnan(val))
                    )
                    else 0.4
                ),
            }

        # -------------------------------- camada de dados (sanitizada) --------------------------------
        cols_for_geojson = list(dict.fromkeys(["geometry", "value"] + t_fields))
        gjson_df = _sanitize_props(gdf_work[cols_for_geojson], cols_for_geojson)

        folium.GeoJson(
            gjson_df,
            name="dados",
            style_function=style_fn,
            highlight_function=lambda feat: {
                "weight": 1.5,
                "color": "#000",
                "fillOpacity": 0.95,
            },
            tooltip=(
                folium.features.GeoJsonTooltip(
                    fields=t_fields,
                    aliases=pt_aliases,
                    localize=True,
                    sticky=True,
                    labels=True,
                )
                if t_fields
                else None
            ),
            pane="pane-dados",
        ).add_to(m)

        # -------------------------------- traçado de estados --------------------------------
        if self.show_state_outline:
            if scope == "estado":
                key_norm = _norm_str(state_filter) if state_filter is not None else ""
                # targets por coluna: se GO -> GO + DF; senão, apenas o estado pedido
                if key_norm in {"go", "goias", "goiás", "52", "5200000"}:
                    targets_by_col = {
                        "abbrev_state": {"go", "df"},
                        "state_abbrev": {"go", "df"},
                        "abrev_state": {"go", "df"},
                        "state_name": {"goias", "distrito federal"},
                        "name_state": {"goias", "distrito federal"},
                        "code_state": {"52", "53", "5200000", "5300000"},
                        "state_code": {"52", "53", "5200000", "5300000"},
                    }
                else:
                    targets_by_col = {
                        c: {key_norm} for c in _guess_state_cols(states.columns)
                    }

                mask_state = pd.Series(False, index=states.index)
                for col in _guess_state_cols(states.columns):
                    vals = states[col].astype(str).map(_norm_str)
                    targets = targets_by_col.get(col, {key_norm})
                    mask_state |= vals.isin(targets)

                uf_gdf = (
                    states[mask_state]
                    if mask_state.any()
                    else gpd.GeoDataFrame(
                        geometry=[unary_union(gdf_work.geometry)], crs=4326
                    )
                )

                folium.GeoJson(
                    uf_gdf[["geometry"]],
                    name="Traçado do Estado",
                    style_function=lambda feat: {
                        "fillOpacity": 0,
                        "color": "#1a1a1a",
                        "weight": 1.6,
                    },
                    pane="pane-contorno",
                    control=True,
                    interactive=False,
                ).add_to(m)
            else:
                folium.GeoJson(
                    states[["geometry"]],
                    name="Traçado de Estados",
                    style_function=lambda feat: {
                        "fillOpacity": 0,
                        "color": "#1a1a1a",
                        "weight": 1.2,
                    },
                    pane="pane-contorno",
                    control=True,
                    interactive=False,
                ).add_to(m)

        # -------------------------------- traçado de regiões (quando Brasil) --------------------------------
        if self.show_region_outline and scope == "brasil":
            regions = self._region_dl.download(year=year_norm, simplified=True).to_crs(
                4326
            )
            folium.GeoJson(
                regions[["geometry"]],
                name="Traçado de Regiões",
                style_function=lambda feat: {
                    "fillOpacity": 0,
                    "color": "#1a1a1a",
                    "weight": 1.2,
                },
                pane="pane-contorno",
                control=True,
                interactive=False,
            ).add_to(m)

        # -------------------------------- legenda / controle --------------------------------
        if self.show_legend:
            legend = _legend_html(
                title=title,
                subtitle=subtitle,
                year=self.year,
                bins=bins_list,
                colors=colors,
            )
            folium.Map.get_root(m).html.add_child(folium.Element(legend))

        folium.LayerControl(collapsed=True).add_to(m)

        if self.output_html is not None:
            with atomic_output(self.output_html) as temporary:
                m.save(str(temporary))

        return m
