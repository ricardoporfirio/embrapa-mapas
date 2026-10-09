# src/models/base_model.py
from __future__ import annotations

from abc import ABC
from typing import Dict, TypedDict
import pandas as pd

from src.core.sidra.enums import CultureStyle


class Label(TypedDict):
    """Estrutura padronizada para rótulos usados nos DataFrames."""

    title: str
    unit: str


class BaseModel(ABC):
    """
    Classe base para modelos que trabalham com DataFrames e metadados (labels).
    - 'descriptions' mapeia um CultureStyle -> Label(title, unit)
    - 'df' é opcional e pode ser definido via set_df
    """

    def __init__(self) -> None:
        # Evita Optional e simplifica validação a jusante
        self.descriptions: Dict[CultureStyle, Label] = {}
        self.df: pd.DataFrame | None = None

    # ---------------------------
    # DataFrame helpers
    # ---------------------------
    def set_df(self, df: pd.DataFrame) -> None:
        """Define o DataFrame principal do modelo."""
        self.df = df

    def has_df(self) -> bool:
        """Retorna True se houver DataFrame definido."""
        return self.df is not None

    # ---------------------------
    # Labels helpers
    # ---------------------------
    def get_label(self, style: CultureStyle) -> Label:
        """Recupera o label (title, unit) para um CultureStyle dado."""
        try:
            return self.descriptions[style]
        except KeyError as e:
            valid = ", ".join(s.name for s in self.descriptions.keys())
            raise KeyError(
                f"Style '{style.name}' não encontrado em descriptions. "
                f"Disponíveis: {valid or 'nenhum cadastrado'}."
            ) from e

    def set_descriptions_on_dataframe(
        self, style: CultureStyle, *, as_attrs: bool = True
    ) -> pd.DataFrame:
        """
        Aplica o label de 'style' ao DataFrame atual.
        - as_attrs=True: salva em df.attrs['title'] e df.attrs['unit'] (não cria colunas)
        - as_attrs=False: cria/atualiza colunas 'title' e 'unit' com valores escalares
        Retorna o próprio DataFrame.
        """
        if self.df is None:
            raise ValueError("DataFrame não definido. Chame set_df primeiro.")

        desc = self.get_label(style)

        if as_attrs:
            self.df.attrs["title"] = desc["title"]
            self.df.attrs["unit"] = desc["unit"]
        else:
            # Valores escalares -> pandas propaga para todas as linhas
            self.df["title"] = desc["title"]
            self.df["unit"] = desc["unit"]

        return self.df

    def get_title(self, style: CultureStyle) -> str:
        """
        Retorna o título do label associado a um estilo de cultura.
        """
        if style not in self.descriptions:
            raise ValueError(f"Estilo de cultura '{style}' não suportado.")
        return self.descriptions[style]["title"]

    def get_unit(self, style: CultureStyle) -> str:
        """
        Retorna a unidade do label associado a um estilo de cultura.
        """
        if style not in self.descriptions:
            raise ValueError(f"Estilo de cultura '{style}' não suportado.")
        return self.descriptions[style]["unit"]

    def get_legend_title(self, style: CultureStyle) -> str:
        """
        Retorna a unidade do label associado a um estilo de cultura.
        """
        if style not in self.descriptions:
            raise ValueError(f"Estilo de cultura '{style}' não suportado.")
        return self.descriptions[style]["legend_title"]
