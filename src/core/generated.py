from src.utils.classification import class_limits
from src.utils.cileite_presets import preset_limits
import ast
import json
from pathlib import Path
import re
from src.core.sidra.base_downloader import _BaseSidraDownloader
from src.models.base_model import BaseModel
from src.core.sidra import CultureStyle
from src.core.job.job_country import job_country
from src.core.job.job_region import job_region
from src.core.job.job_state import job_state
from src.core.job.job_municipality import job_municipality
from src.core.make_map_dynamic import DynamicMap
from src.core.make_map_static import StaticMap
from src.utils.create_folder import FolderCreator
import pandas as pd
import numpy as np
from math import log2, ceil
from typing import Optional
from src.utils.define_colors import ColorPalette

# Suporte opcional a emissão de progresso (SSE)
from src.core.progress import ProgressMeta

from src.core.poster import render_poster


class Generated:
    def __init__(
        self,
        base_folder: str,
        style_folder: str,
        period: list[int],
        shape_year: int,
        model: BaseModel,
        culture_style: CultureStyle,
        bins: dict,
        multiplier: int,
        cls_milking=_BaseSidraDownloader,
        cls_production=_BaseSidraDownloader,
        color_code="YlOrRd",
        is_density=False,
        is_productivity=False,
        progress: Optional[ProgressMeta] = None,
        basemap: str = "none",
        fixed_bins: bool = False,
    ) -> None:
        # mantém exatamente o contrato original (instâncias)
        self.model = model
        self.period = period
        self.culture_style = culture_style
        self.base_folder = base_folder
        self.style_folder = style_folder
        self.bins = bins
        self.color_code = color_code

        self.pallet = ColorPalette(self.color_code)

        self.shape_year = shape_year

        self.milking = cls_milking
        self.production = cls_production

        self.is_density = is_density
        self.is_productivity = is_productivity

        self.multiplier = multiplier


        self.ufs = (
            "AC",
            "AL",
            "AM",
            "AP",
            "BA",
            "CE",
            "ES",
            "GO",
            "MA",
            "MG",
            "MS",
            "MT",
            "PA",
            "PB",
            "PE",
            "PI",
            "PR",
            "RJ",
            "RN",
            "RO",
            "RR",
            "RS",
            "SC",
            "SE",
            "SP",
            "TO",
        )

        self.regs = ("norte", "nordeste", "centro-oeste", "sudeste", "sul")

        # emissor de progresso (opcional; não altera a lógica)
        self.progress = progress
        self.tiles = None if basemap == "none" else "OpenStreetMap"
        self.fixed_bins = fixed_bins and bins.get("mode") != "cileite"

    def bin_df(self, df, config_str):
        return class_limits(df["value"], config_str)

    def map_bins(self, bins, year, territory="brasil"):
        if self.bins.get("mode") == "cileite":
            return preset_limits(self.bins["indicator"], year, territory)
        return bins

    def run(self):
        # total de tarefas (por ano): 2 * (1 + 5 + 26) = 64
        total_per_year = 2 * (1 + len(self.regs) + len(self.ufs))
        grand_total = len(self.period) * total_per_year
        cur = 0
        if self.progress:
            self.progress.start(grand_total)

        shared_bins = None
        prepared = {}
        if self.fixed_bins:
            prepared = {year: self._save_database(year) for year in self.period}
            shared_bins = class_limits(pd.concat([df["value"] for df in prepared.values()], ignore_index=True), self.bins)

        for year in self.period:
            df = prepared.pop(year) if self.fixed_bins else self._save_database(year)
            bins = self.map_bins(None, year) if self.bins.get("mode") == "cileite" else (shared_bins if shared_bins is not None else self.bin_df(df, self.bins))

            # Gera os mapas interativos a nível brasil
            FolderCreator().create_folder(
                f"mapas/{self.base_folder}/{self.style_folder}/{year}/"
            )

            FolderCreator().create_folder(
                f"imagens/{self.base_folder}/{self.style_folder}/{year}/"
            )

            FolderCreator().create_folder(
                f"poster/{self.base_folder}/{self.style_folder}/{year}/"
            )

            # ===== Dinâmico: Brasil
            if self.progress:
                self.progress.activity(f"Gerando mapa interativo: Brasil — {year}", year=year)
            DynamicMap(
                tiles=self.tiles,
                year=year,
                bins=bins,  # ou uma lista de quebras [100, 300, 600, 900, float("inf")]
                color_code=self.color_code,
                show_region_outline=True,  # mostra contorno das 5 regiões
                show_state_outline=True,  # mostra contorno de UFs
                tooltip_fields=("territory", "value", "unit"),
                output_html=f"mapas/{self.base_folder}/{self.style_folder}/{year}/brasil.html",
            ).build(df)
            cur += 1
            if self.progress:
                self.progress.step(
                    label="Interativo: Brasil",
                    group="dynamic_brazil",
                    year=year,
                    current=cur,
                    total=grand_total,
                )

            # ===== Dinâmico: Regiões
            for reg in self.regs:
                if self.progress:
                    self.progress.activity(f"Gerando mapa interativo: {reg} — {year}", year=year)
                DynamicMap(
                    tiles=self.tiles,
                    year=year,
                    bins=bins,
                    color_code=self.color_code,
                    region=reg,  # filtra o gdf para a região
                    show_state_outline=True,  # mantém contorno das UFs
                    tooltip_fields=("territory", "value", "unit"),
                    output_html=f"mapas/{self.base_folder}/{self.style_folder}/{year}/{reg}.html",
                ).build(df)
                cur += 1
                if self.progress:
                    self.progress.step(
                        label=f"Interativo: Região {reg}",
                        group="dynamic_regions",
                        year=year,
                        current=cur,
                        total=grand_total,
                    )

            # ===== Dinâmico: UFs
            for uf in self.ufs:
                if self.progress:
                    self.progress.activity(f"Gerando mapa interativo: {uf} — {year}", year=year)
                DynamicMap(
                    tiles=self.tiles,
                    year=year,
                    bins=self.map_bins(bins, year, uf),
                    color_code=self.color_code,
                    state=uf,  # filtra o gdf para a UF
                    show_state_outline=True,
                    tooltip_fields=("territory", "value", "unit"),
                    output_html=f"mapas/{self.base_folder}/{self.style_folder}/{year}/{uf}.html",
                ).build(df)
                cur += 1
                if self.progress:
                    self.progress.step(
                        label=f"Interativo: {uf}",
                        group="dynamic_states",
                        year=year,
                        current=cur,
                        total=grand_total,
                    )

            # ===== Estático: Brasil
            if self.progress:
                self.progress.activity(f"Gerando mapa estático: Brasil — {year}", year=year)
            StaticMap(
                year=year,
                bins=bins,
                color_code=self.color_code,
                dpi=300,
                figsize=8.0,
                show_legend=False,
                output_path=f"imagens/{self.base_folder}/{self.style_folder}/{year}/brasil.png",
            ).build(df)
            cur += 1
            if self.progress:
                self.progress.step(
                    label="Estático: Brasil",
                    group="static_brazil",
                    year=year,
                    current=cur,
                    total=grand_total,
                )

            render_poster(
                title=self.model.get_title(self.culture_style),
                subtitle=f"Brasil — {year}",
                image_path=f"imagens/{self.base_folder}/{self.style_folder}/{year}/brasil.png",
                legend_title=self.model.get_legend_title(self.culture_style),
                measure_unit=self.model.get_unit(self.culture_style),
                bins=bins,
                colors=self.pallet.generate(len(bins)),
                year=year,
                output=f"poster/{self.base_folder}/{self.style_folder}/{year}/brasil.png",
            )

            # ===== Estático: Regiões
            for reg in self.regs:
                if self.progress:
                    self.progress.activity(f"Gerando mapa estático: {reg} — {year}", year=year)
                StaticMap(
                    year=year,
                    bins=bins,
                    color_code=self.color_code,
                    dpi=300,
                    figsize=8.0,
                    show_legend=False,
                    region=reg,
                    output_path=f"imagens/{self.base_folder}/{self.style_folder}/{year}/{reg}.png",
                ).build(df)

                render_poster(
                    title=self.model.get_title(self.culture_style),
                    subtitle=f"{reg.capitalize()} — {year}",
                    image_path=f"imagens/{self.base_folder}/{self.style_folder}/{year}/{reg}.png",
                    legend_title=self.model.get_legend_title(self.culture_style),
                    measure_unit=self.model.get_unit(self.culture_style),
                    bins=bins,
                    colors=self.pallet.generate(len(bins)),
                    year=year,
                    output=f"poster/{self.base_folder}/{self.style_folder}/{year}/{reg}.png",
                )

                cur += 1
                if self.progress:
                    self.progress.step(
                        label=f"Estático: Região {reg}",
                        group="static_regions",
                        year=year,
                        current=cur,
                        total=grand_total,
                    )

            # ===== Estático: UFs
            for uf in self.ufs:
                if self.progress:
                    self.progress.activity(f"Gerando mapa estático: {uf} — {year}", year=year)
                StaticMap(
                    year=year,
                    bins=self.map_bins(bins, year, uf),
                    color_code=self.color_code,
                    dpi=300,
                    figsize=8.0,
                    show_legend=False,
                    state=uf,
                    output_path=f"imagens/{self.base_folder}/{self.style_folder}/{year}/{uf}.png",
                ).build(df)

                render_poster(
                    title=self.model.get_title(self.culture_style),
                    subtitle=f"{uf} — {year}",
                    image_path=f"imagens/{self.base_folder}/{self.style_folder}/{year}/{uf}.png",
                    legend_title=self.model.get_legend_title(self.culture_style),
                    measure_unit=self.model.get_unit(self.culture_style),
                    bins=self.map_bins(bins, year, uf),
                    colors=self.pallet.generate(len(self.map_bins(bins, year, uf))),
                    year=year,
                    output=f"poster/{self.base_folder}/{self.style_folder}/{year}/{uf}.png",
                )

                cur += 1
                if self.progress:
                    self.progress.step(
                        label=f"Estático: {uf}",
                        group="static_states",
                        year=year,
                        current=cur,
                        total=grand_total,
                    )

        if self.progress:
            self.progress.done()

    def _save_database(self, year: int):
        common = dict(
            year=year, shape_year=self.shape_year, dir_name=self.base_folder,
            style_folder=self.style_folder, culture_style=self.culture_style,
            model=self.model, downloader_mk=self.milking, downloader_pr=self.production,
            is_density=self.is_density, is_productivity=self.is_productivity,
        )
        result = None
        for label, job in (("Brasil", job_country), ("Regiões", job_region),
                           ("Estados", job_state), ("Municípios", job_municipality)):
            if self.progress:
                self.progress.activity(f"Preparando base: {label} — {year}", year=year)
            result = job(**common, **({"progress": self.progress} if job is job_municipality else {}))
            if self.progress:
                self.progress.activity(f"Base pronta: {label} — {year}", year=year)
        return result
