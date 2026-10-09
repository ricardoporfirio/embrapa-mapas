# src/core/sidra/enums.py
from enum import Enum


class CultureStyle(Enum):

    MILKING = 1
    PRODUCTION = 2
    DENSITY_MILKING = 3
    DENSITY_PRODUCTION = 4
    PRODUCTIVITY = 5


class Culture(Enum):
    """Códigos das tabelas SIDRA para diferentes culturas de leite."""

    COW_MILKING = 94  # Ordenha de vacas
    COW_PRODUCTION = 74  # Produção de leite de vaca
    GOAT_MILKING = 6929  # Ordenha de cabras
    GOAT_PRODUCTION = 6928  # Produção de leite de cabras
    SHEEP_MILKING = 6931  # Ordenha de ovelhas
    SHEEP_PRODUCTION = (
        6931  # Produção de leite de ovelhas (mesma tabela; muda variável)
    )


class TerritorialLevel(Enum):
    """Níveis territoriais aceitos pelo SIDRA/IBGE."""

    COUNTRY = 1  # Brasil
    REGION = 2  # Região (Norte, Sul, etc.)
    STATE = 3  # Estado (UF)
    MUNICIPALITY = 6  # Município
