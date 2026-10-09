# src/models/cow.py
"""Modelo de vacas via BaseModel (labels obrigatórios, DF opcional)."""

from __future__ import annotations

import pandas as pd

from src.models.base_model import BaseModel, Label
from src.core.sidra.enums import CultureStyle


class CowModel(BaseModel):
    def __init__(self) -> None:
        super().__init__()
        self.name = "Bovinos"

        # Mapeia cada estilo de cultura para seu título e unidade padrão
        self.descriptions = {
            CultureStyle.MILKING: Label(
                title="Vacas Ordenhadas",
                unit="Em cabeças",
                legend_title="Vacas Ordenhadas",
            ),
            CultureStyle.PRODUCTION: Label(
                title="Produção de leite de vaca",
                unit="Em 1000 L",
                legend_title="Produção de leite",
            ),
            CultureStyle.DENSITY_MILKING: Label(
                title="Densidade de vacas",
                unit="Em cabeças / km²",
                legend_title="Densidade de vacas",
            ),
            CultureStyle.DENSITY_PRODUCTION: Label(
                title="Densidade de produção de leite",
                unit="Em L / km²",
                legend_title="Densidade de produção",
            ),
            CultureStyle.PRODUCTIVITY: Label(
                title="Produtividade de leite de vaca",
                unit="Em L / cabeça",
                legend_title="Produtividade (leite)",
            ),
        }
