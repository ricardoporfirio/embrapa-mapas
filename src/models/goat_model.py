# src/models/goat.py
"""Modelo de cabras via BaseModel (labels obrigatórios, DF opcional)."""

from __future__ import annotations
import pandas as pd

from src.models.base_model import BaseModel, Label
from src.core.sidra.enums import CultureStyle


class GoatModel(BaseModel):
    def __init__(self) -> None:
        super().__init__()
        self.name = "Caprinos"

        self.descriptions = {
            CultureStyle.MILKING: Label(
                title="Cabras Ordenhadas",
                unit="Em cabeças",
                legend_title="Cabras Ordenhadas",
            ),
            CultureStyle.PRODUCTION: Label(
                title="Produção de leite de cabra",
                unit="Em 1000 L",
                legend_title="Produção de leite",
            ),
            CultureStyle.DENSITY_MILKING: Label(
                title="Densidade de cabras",
                unit="Em cabeças / km²",
                legend_title="Densidade de cabras",
            ),
            CultureStyle.DENSITY_PRODUCTION: Label(
                title="Densidade de produção de leite",
                unit="Em L / km²",
                legend_title="Densidade de produção",
            ),
            CultureStyle.PRODUCTIVITY: Label(
                title="Produtividade de leite de cabra",
                unit="Em L / cabeça",
                legend_title="Produtividade (leite)",
            ),
        }
