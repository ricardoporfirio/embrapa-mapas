# make_map_static.py
"""
Mapa ESTÁTICO (Matplotlib) com choropleth pelos `values` e traçado APENAS dos ESTADOS.

Ajustes pedidos + melhorias de qualidade:
- Ignorar micro-ilhas SEMPRE ao calcular o enquadramento (sem flag). O limiar é controlado por
  `island_area_ratio` (ex.: 0.01 => descarta partes <1% da maior área).
- `bins` em lista: `+inf` é anexado automaticamente.
- Canvas quadrado e aspecto 1:1.
- Bordas mais suaves (join/cap "round"), antialias ligado.
- Exportação vetorial (PDF/SVG) com opção de rasterizar apenas os preenchimentos.
- Legenda com tipografia nítida e layout que evita cortes.
"""

from __future__ import annotations

from src.utils.atomic import atomic_output

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Sequence, Tuple
import unicodedata

import geopandas as gpd
import matplotlib as mpl

mpl.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

from src.core.geobr_shapes import StateDownloader, RegionDownloader
from src.utils.define_colors import ColorPalette


# ---------------- helpers ----------------
from src.utils.classification import format_number as _pt_number, labels_from_bins as _labels_from_bins


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


def _normalize_year_for_geobr(year: int) -> int:
    return 2020 if year > 2000 else year


def _square_extent_from_gdf(ax, gdf: gpd.GeoDataFrame, pad_ratio: float = 0.02) -> None:
    """Define um bbox QUADRADO a partir dos bounds do gdf já em SIRGAS 2000."""
    minx, miny, maxx, maxy = gdf.total_bounds
    width = maxx - minx
    height = maxy - miny
    L = max(width, height)
    pad = L * pad_ratio
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0
    half = L / 2.0
    ax.set_xlim(cx - half - pad, cx + half + pad)
    ax.set_ylim(cy - half - pad, cy + half + pad)
    ax.set_aspect("equal", adjustable="box")


def _filter_micro_islands(gdf: gpd.GeoDataFrame, area_ratio: float) -> gpd.GeoDataFrame:
    """
    Remove geometrias muito pequenas (micro-ilhas) tomando como referência a maior peça.
    O cálculo de área é feito em metros (EPSG:3857) apenas para ranking relativo.
    """
    if gdf.empty:
        return gdf
    # explode pra partes
    try:
        exploded = gdf.explode(index_parts=False, ignore_index=True)
    except TypeError:
        exploded = gdf.explode(index_parts=False)
        exploded.reset_index(drop=True, inplace=True)

    g_3857 = exploded.to_crs(3857)
    areas = g_3857.geometry.area
    max_area = float(areas.max()) if not areas.isna().all() else 0.0
    if max_area <= 0:
        return gdf
    keep = areas >= (max_area * area_ratio)
    filtered = exploded.loc[keep].copy()
    return filtered.to_crs(4674)


def _apply_line_styles(ax, joinstyle: str, capstyle: str) -> None:
    """
    Aplica join/cap 'round' (ou outro) em coleções de linhas/patches já desenhadas.
    Nem todos os artistas expõem diretamente; tratamos LineCollection e PathCollection.
    """
    for artist in ax.get_children():
        # Line2D
        if hasattr(artist, "set_solid_joinstyle"):
            try:
                artist.set_solid_joinstyle(joinstyle)
                artist.set_solid_capstyle(capstyle)
            except Exception:
                pass
        # LineCollection
        if hasattr(artist, "set_joinstyle"):
            try:
                artist.set_joinstyle(joinstyle)
                artist.set_capstyle(capstyle)
            except Exception:
                pass
        # Patch/PathCollection: bordas
        if hasattr(artist, "set_joinstyle"):
            try:
                artist.set_joinstyle(joinstyle)
            except Exception:
                pass
        if hasattr(artist, "set_capstyle"):
            try:
                artist.set_capstyle(capstyle)
            except Exception:
                pass


def _detect_format_and_params(
    output_path: Path | None, explicit_fmt: str | None
) -> Tuple[str, dict]:
    """
    Decide formato de saída e parâmetros do savefig.
    - Se explicit_fmt for fornecido, usa-o.
    - Caso contrário, deduz do sufixo do arquivo; se não houver, usa 'png'.
    """
    if explicit_fmt:
        fmt = explicit_fmt.lower()
    else:
        fmt = "png"
        if output_path is not None and output_path.suffix:
            fmt = output_path.suffix.replace(".", "").lower()

    # Parâmetros padrão
    save_kws = {
        "bbox_inches": "tight",
        "pad_inches": 0.03,
    }
    # Para formatos vetoriais, evitar DPI alto (não necessário) e manter transparência do facecolor
    if fmt in {"pdf", "svg"}:
        pass
    else:
        pass
    return fmt, save_kws


# ------- helpers extras para robustez GO -> DF -------
def _norm_str(x: Any) -> str:
    s = str(x) if x is not None else ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.strip().lower()


def _mask_for_states(df: pd.DataFrame, targets: set[str]) -> pd.Series:
    """Cria uma máscara OR sobre todas as colunas possíveis de estado (sigla, nome, código)."""
    poss = _guess_state_cols(df.columns)
    # garantir cobrir possíveis nomes de coluna de nome do estado
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


# ---------------- classe principal ----------------
@dataclass
class StaticMap:
    year: int = 2022
    bins: int | Sequence[float] = 5
    color_code: str = "Blues"
    figsize: float | tuple[float, float] = 8.0
    dpi: int = 300

    # estilo
    edgecolor_states: str = "#1a1a1a"
    linewidth_states: float = 1.2
    edgecolor_data: str = "none"
    linewidth_data: float = 0.0
    background_color: str = "white"

    # controles finos de render
    line_joinstyle: str = "round"  # "miter" | "round" | "bevel"
    line_capstyle: str = "round"  # "butt" | "round" | "projecting"
    antialiased: bool = True
    rasterize_fills: bool = False  # se True, mantém contornos vetoriais e áreas raster
    states_simplified: bool = True  # use False para máxima fidelidade do contorno

    # filtros
    scope: str = "brasil"
    region: str | None = None
    state: str | int | None = None
    state_filter: Any | None = None

    # legenda / saída
    show_legend: bool = True
    legend_title: str | None = None
    output_path: str | Path | None = None

    # formato de saída (auto pelo sufixo de output_path; usa PNG se não houver)
    output_format: str | None = None  # "png" | "pdf" | "svg" | None(autodetect)

    # enquadramento
    extent_reference: str = "states"  # "states" | "data" | "union"
    island_area_ratio: float = 0.01  # SEMPRE filtramos micro-ilhas com esse limiar

    _state_dl: Any | None = None
    _region_dl: Any | None = None

    # --------- utils ---------
    def _get_downloaders(self):
        if self._state_dl is None:
            self._state_dl = StateDownloader()
        if self._region_dl is None:
            self._region_dl = RegionDownloader()

    def _filter_region_on_gdf(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        region_to_states = {
            "norte": ["AC", "AP", "AM", "PA", "RO", "RR", "TO"],
            "nordeste": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
            "centro-oeste": ["DF", "GO", "MT", "MS"],
            "sudeste": ["ES", "MG", "RJ", "SP"],
            "sul": ["PR", "RS", "SC"],
        }
        reg_key = self.region.strip().lower()
        if reg_key not in region_to_states:
            raise ValueError(
                f"Região '{self.region}' inválida. Opções: {list(region_to_states.keys())}"
            )
        poss_cols = [
            c
            for c in ["abbrev_state", "state_abbrev", "abrev_state"]
            if c in gdf.columns
        ]
        if not poss_cols:
            raise KeyError(
                "Para usar 'region', o gdf precisa ter uma coluna de sigla de estado."
            )
        return gdf[gdf[poss_cols[0]].isin(region_to_states[reg_key])].copy()

    def _filter_state_on_gdf(self, gdf: gpd.GeoDataFrame, key: str) -> gpd.GeoDataFrame:
        poss = _guess_state_cols(gdf.columns)
        if not poss:
            raise KeyError(
                "Para usar 'state', o gdf precisa ter coluna de UF, nome ou código do estado."
            )
        mask = pd.Series(False, index=gdf.index)
        for col in poss:
            mask |= gdf[col].astype(str).str.lower() == key
        return gdf[mask].copy()

    def _subset_states_layer(
        self, states: gpd.GeoDataFrame, user_subset: gpd.GeoDataFrame
    ) -> gpd.GeoDataFrame:
        poss_user = _guess_state_cols(user_subset.columns)
        if not poss_user:
            return states
        keys = set()
        for col in poss_user:
            keys.update(user_subset[col].astype(str).str.lower().unique().tolist())
        poss_states = _guess_state_cols(states.columns)
        if not poss_states:
            return states
        mask = pd.Series(False, index=states.index)
        for col in poss_states:
            mask |= states[col].astype(str).str.lower().isin(keys)
        return states[mask].copy() if mask.any() else states

    # --------- build ---------
    def build(self, gdf: gpd.GeoDataFrame):
        if gdf is None:
            raise ValueError("`gdf` é obrigatório em StaticMap.build(gdf=...).")
        if "geometry" not in gdf.columns:
            raise ValueError("gdf precisa conter a coluna 'geometry'.")
        if "value" not in gdf.columns:
            raise ValueError("gdf precisa conter a coluna 'value'.")

        # Hints globais de renderização (nitidez)
        mpl.rcParams.update(
            {
                "text.antialiased": self.antialiased,
                "patch.antialiased": self.antialiased,
                "lines.antialiased": self.antialiased,
                "agg.path.chunksize": 0,
            }
        )

        self._get_downloaders()
        gdf_user = gdf.to_crs(4674).copy()

        if self.region and self.state:
            raise ValueError("Use apenas um de 'region' ou 'state', não ambos.")

        # filtros nos dados
        gdf_work = gdf_user
        scope = "brasil"
        if self.region and not self.state:
            gdf_work = self._filter_region_on_gdf(gdf_user)
            scope = "regiao"
        if self.state and not self.region:
            key = str(self.state).strip().lower()
            gdf_work = self._filter_state_on_gdf(gdf_user, key)
            scope = "estado"
        if gdf_work.empty:
            raise ValueError("Após filtros, não há geometrias em `gdf`.")

        # estados para contorno (permite desativar simplificação p/ máxima qualidade)
        year = _normalize_year_for_geobr(self.year)
        states = self._state_dl.download(
            year=year, simplified=self.states_simplified
        ).to_crs(4674)

        if scope == "brasil":
            states_to_draw = states

        elif self.region:
            # garante o contorno de toda a região — inclui DF no Centro-Oeste
            region_to_states = {
                "norte": ["AC", "AP", "AM", "PA", "RO", "RR", "TO"],
                "nordeste": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
                "centro-oeste": ["DF", "GO", "MT", "MS"],
                "sudeste": ["ES", "MG", "RJ", "SP"],
                "sul": ["PR", "RS", "SC"],
            }
            reg_key = self.region.strip().lower()
            poss_states = _guess_state_cols(states.columns)
            mask = pd.Series(False, index=states.index)
            for col in poss_states:
                mask |= (
                    states[col].astype(str).str.upper().isin(region_to_states[reg_key])
                )
            states_to_draw = states[mask].copy()

        else:
            # scope == "estado"
            # 1) Base: estados presentes no gdf_work
            states_to_draw = self._subset_states_layer(states, gdf_work)

            # 2) 🚩 Forçar inclusão do DF quando o estado pedido for Goiás
            s = _norm_str(self.state)
            is_go = s in {
                "go",
                "goias",
                "goiás",
                "52",
                "5200000",
            }  # aceita sigla/nome/códigos
            if is_go:
                mask_df = _mask_for_states(
                    states, {"df", "distrito federal", "53", "5300000"}
                )
                if mask_df.any():
                    states_to_draw = pd.concat(
                        [states_to_draw, states.loc[mask_df]], ignore_index=True
                    )
                    # Deduplicar por uma coluna estável, se existir
                    for cand in [
                        "code_state",
                        "state_code",
                        "abbrev_state",
                        "state_abbrev",
                        "name_state",
                        "state_name",
                    ]:
                        if cand in states_to_draw.columns:
                            states_to_draw = states_to_draw.drop_duplicates(
                                subset=cand, keep="first"
                            )
                            break

            # 3) Também garantir um PATCH de dados para o DF (senão o interior fica "vazio")
            if is_go:
                mask_df = _mask_for_states(
                    states, {"df", "distrito federal", "53", "5300000"}
                )
                if mask_df.any():
                    df_geom = states.loc[mask_df, "geometry"].values[0]
                    row = {
                        "geometry": df_geom,
                        # NaN => cai na cor de "sem dado" (#cccccc). Troque por uma métrica se preferir.
                        "value": np.nan,
                        "variable": (
                            gdf_work.get("variable", pd.Series(["Mapa"])).iloc[0]
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
                    df_dummy = gpd.GeoDataFrame(
                        [row], geometry="geometry", crs=states.crs
                    ).to_crs(4674)

                    # evita duplicar se já existir algo do DF nos dados
                    poss_user = _guess_state_cols(gdf_work.columns)
                    already = False
                    if poss_user:
                        mask_already = pd.Series(False, index=gdf_work.index)
                        for col in poss_user:
                            mask_already |= (
                                gdf_work[col].astype(str).str.upper().eq("DF")
                            )
                        already = bool(mask_already.any())
                    if not already:
                        gdf_work = pd.concat([gdf_work, df_dummy], ignore_index=True)

        # --- bins/paleta/classificação (depois de injetar DF, para ele também ganhar cor) ---
        if isinstance(self.bins, int):
            bins_list = _equal_bins_from_values(gdf_work["value"], self.bins)
        else:
            bins_list = list(self.bins) or None
            if bins_list is None:
                raise ValueError("Lista de `bins` não pode ser vazia.")
            if not np.isinf(bins_list[-1]):
                bins_list.append(float("inf"))
        bins_list = list(np.sort(np.array(bins_list, dtype=float)))

        try:
            palette = ColorPalette(self.color_code).generate(len(bins_list))
        except Exception:
            default = ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"]
            k = len(bins_list)
            palette = (default * ((k + len(default) - 1) // len(default)))[:k]

        vals = pd.to_numeric(gdf_work["value"], errors="coerce")
        cat_idx = pd.Series(
            np.digitize(vals, bins_list, right=True), index=gdf_work.index
        )
        cat_idx = cat_idx.clip(lower=0, upper=len(bins_list) - 1)
        gdf_work["_color"] = cat_idx.map(
            lambda i: palette[int(i)] if pd.notna(i) else "#cccccc"
        )

        gdf_work.loc[vals.isna(), "_color"] = "#cccccc"

        # figura 1:1 quadrada (com layout que evita cortes)
        if isinstance(self.figsize, (int, float)):
            figsize = (float(self.figsize), float(self.figsize))
        else:
            side = float(max(self.figsize))
            figsize = (side, side)

        fig = plt.figure(
            figsize=figsize,
            dpi=self.dpi,
            facecolor=self.background_color,
            layout="constrained",
        )
        ax = fig.add_subplot(111, facecolor=self.background_color)

        # 1) dados preenchidos (opcionalmente rasterizados para PDF/SVG leves)
        gdf_work.plot(
            ax=ax,
            color=gdf_work["_color"],
            edgecolor=self.edgecolor_data,
            linewidth=self.linewidth_data,
            antialiased=self.antialiased,
        )
        if self.rasterize_fills:
            for artist in ax.collections:
                try:
                    artist.set_rasterized(True)
                except Exception:
                    pass

        # 2) contorno dos ESTADOS
        states_to_draw.plot(
            ax=ax,
            facecolor="none",
            edgecolor=self.edgecolor_states,
            linewidth=self.linewidth_states,
            antialiased=self.antialiased,
        )

        # aplicar join/cap arredondado nas coleções existentes
        _apply_line_styles(ax, self.line_joinstyle, self.line_capstyle)

        ax.axis("off")

        # *** Enquadramento (SEMPRE filtra micro-ilhas) ***
        if self.extent_reference == "data":
            ref = gdf_work
        elif self.extent_reference == "union":
            ref = gpd.GeoDataFrame(
                geometry=pd.concat(
                    [gdf_work.geometry, states_to_draw.geometry], ignore_index=True
                ),
                crs=4674,
            )
        else:  # "states"
            ref = states_to_draw

        ref = _filter_micro_islands(ref, self.island_area_ratio)
        _square_extent_from_gdf(ax, ref)

        # legenda
        if self.show_legend:
            labels = _labels_from_bins(bins_list)
            handles = [
                Patch(
                    facecolor=palette[i],
                    edgecolor="#2b2b2b",
                    linewidth=0.3,
                    label=labels[i],
                )
                for i in range(len(labels))
            ]
            handles.append(Patch(facecolor="#cccccc", edgecolor="#2b2b2b", label="Sem informação"))
            title = self.legend_title
            if title is None:
                title = str(gdf_work.get("variable", pd.Series(["Mapa"])).iloc[0])
                unit = str(gdf_work.get("unit", pd.Series([""])).iloc[0])
                if unit and unit != "nan":
                    title = f"{title} ({unit})"
            leg = ax.legend(
                handles=handles,
                title=title,
                loc="lower right",
                frameon=True,
                framealpha=1.0,
                borderpad=0.5,
                handlelength=1.2,
                handletextpad=0.5,
                fontsize=8,
            )
            if leg.get_title():
                leg.get_title().set_fontsize(9)

        # salvar (autoformato por sufixo; PNG se não houver)
        if self.output_path is not None:
            out = Path(self.output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            fmt, save_kws = _detect_format_and_params(out, self.output_format)

            if fmt not in {"pdf", "svg"}:
                save_kws["dpi"] = self.dpi

            target = out if out.suffix else out.with_suffix(f".{fmt}")
            if fmt == "png":
                # Registra o retângulo exato do eixo e o enquadramento geográfico.
                # O pôster usa esses dados, nunca as bordas dos polígonos, para escala/coordenadas.
                fig.canvas.draw()
                fig.set_layout_engine("none")
                x0, y0, width, height = ax.get_position().bounds
                cartography = {
                    "version": 1, "crs": "EPSG:4674",
                    "extent": [*ax.get_xlim(), *ax.get_ylim()],
                    "axes": [x0, y0, width, height],
                }
                save_kws["metadata"] = {"embrapa_cartography": json.dumps(cartography)}
            with atomic_output(target) as temporary:
                fig.savefig(temporary, facecolor=self.background_color, format=fmt, **save_kws)
        plt.close(fig)
        return fig, ax
