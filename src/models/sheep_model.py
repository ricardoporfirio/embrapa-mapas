# src/models/sheep.py
"""Modelo de ovelhas via BaseModel (labels obrigatórios, DF opcional)."""

from __future__ import annotations
import pandas as pd

from src.models.base_model import BaseModel, Label
from src.core.sidra.enums import CultureStyle


class SheepModel(BaseModel):
    def __init__(self) -> None:
        super().__init__()
        self.name = "Ovinos"

        self.descriptions = {
            CultureStyle.MILKING: Label(
                title="Ovelhas Ordenhadas",
                unit="Em cabeças",
                legend_title="Ovelhas Ordenhadas",
            ),
            CultureStyle.PRODUCTION: Label(
                title="Produção de leite de ovelha",
                unit="Em 1000 L",
                legend_title="Produção de leite",
            ),
            CultureStyle.DENSITY_MILKING: Label(
                title="Densidade de ovelhas",
                unit="Em cabeças / km²",
                legend_title="Densidade de ovelhas",
            ),
            CultureStyle.DENSITY_PRODUCTION: Label(
                title="Densidade de produção de leite",
                unit="Em L / km²",
                legend_title="Densidade de produção",
            ),
            CultureStyle.PRODUCTIVITY: Label(
                title="Produtividade de leite de ovelha",
                unit="Em L / cabeça",
                legend_title="Produtividade (leite)",
            ),
        }
