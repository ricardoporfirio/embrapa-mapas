# src/.../_base_sidra_downloader.py
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from sidrapy.resources.handler import get_url
from sidrapy.resources.http_client import HttpClient
from src.utils.network import get_response, DownloadError
from src.core.progress import report_activity

from .enums import Culture, TerritorialLevel


class _BaseSidraDownloader(ABC):
    """Base abstrata para consultas ao SIDRA com padronização e cache.

    Subclasses devem definir:
        - culture (Culture)
        - variable (str | list[str] | None)
        - classifications (dict[str, str] | None)

    Retorno padronizado (após limpeza/normalização):
        - territory_code (int)
        - territory (str)
        - value (float)
    """

    # cache compartilhado entre todas as subclasses
    _CACHE_TTL = timedelta(days=730)  # ~2 anos
    _CACHE: dict[tuple, tuple[datetime, pd.DataFrame]] = {}

    # ---- Atributos a serem definidos nas subclasses -------------------------
    @property
    @abstractmethod
    def culture(self) -> Culture: ...

    @property
    @abstractmethod
    def variable(self) -> str | list[str] | None: ...

    @property
    @abstractmethod
    def classifications(self) -> dict[str, str] | None: ...

    # ---- API pública --------------------------------------------------------
    def download(
        self,
        territorial_level: TerritorialLevel,
        period: int | str = 2017,
    ) -> pd.DataFrame:
        """Executa a consulta ao SIDRA e retorna DF padronizado."""
        cache_key = self._make_cache_key(
            culture=self.culture,
            territorial_level=territorial_level,
            classifications=self.classifications,
            variable=self.variable,
            period=period,
        )
        cached = self._cache_get(cache_key)
        if cached is not None:
            report_activity(f"SIDRA: usando cache de {territorial_level.name.lower()} — {period}")
            return cached

        # Consulta
        url = get_url(
            table_code=self.culture.value,
            territorial_level=territorial_level.value,
            ibge_territorial_code="all",
            variable=self.variable,
            classifications=self.classifications,
            period=period,
        )
        label = f"SIDRA tabela {self.culture.value}, {territorial_level.name.lower()}, ano {period}"
        with HttpClient.get_legacy_session() as session:
            response = get_response(url, label=label, session=session)
        try:
            data = response.json()
        except ValueError as error:
            raise DownloadError(f"{label}: o IBGE retornou uma resposta inválida.") from error
        if not isinstance(data, list):
            raise DownloadError(f"{label}: o IBGE não retornou uma tabela de dados.")
        df = pd.DataFrame(data)

        # Limpeza / padronização (colunas D1C/D1N/V -> territory_code/territory/value)
        df = self._clean(df)

        # Normalização de códigos para casar com o GeoDataFrame
        df = self._normalize_codes(df, territorial_level)

        # Cacheia e retorna
        self._cache_set(cache_key, df)
        return df

    # ---- Helpers de limpeza -------------------------------------------------
    @staticmethod
    def _clean(df: pd.DataFrame) -> pd.DataFrame:
        # remove a primeira linha (cabeçalho redundante) e reorganiza índice
        df = df.iloc[1:].reset_index(drop=True)

        # valida colunas esperadas
        expected = {"D1C", "D1N", "V"}
        missing = expected - set(df.columns)
        if missing:
            raise ValueError(
                f"Colunas esperadas ausentes no retorno do SIDRA: {missing}"
            )

        # conversões / coerção
        df["D1C"] = df["D1C"].astype(int)
        df["V"] = pd.to_numeric(df["V"], errors="coerce")

        # reduz e renomeia
        return df[["D1C", "D1N", "V"]].rename(
            columns={"D1C": "territory_code", "D1N": "territory", "V": "value"}
        )

    # ---- Normalização de códigos -------------------------------------------
    @staticmethod
    def _normalize_codes(
        df: pd.DataFrame, territorial_level: TerritorialLevel
    ) -> pd.DataFrame:
        """Ajusta códigos do SIDRA para o padrão dos GeoDataFrames.

        Regras atuais:
        - País (Brasil): forçar `territory_code = 76` (código IBGE do país).
        - Demais níveis: manter como vem do SIDRA.
        """
        df = df.copy()

        # Heurísticas para detectar nível país
        level_name = getattr(territorial_level, "name", "")
        level_val = getattr(territorial_level, "value", "")

        country_level_markers = {
            "COUNTRY",
            "PAIS",
            "NACIONAL",
            "NATION",
            "N1",
            "LEVEL_COUNTRY",
        }
        is_country_level = (
            str(level_name).upper() in country_level_markers
            or str(level_val).upper() in country_level_markers
            or (
                len(df) == 1
                and str(df["territory"].iloc[0]).strip().lower() in {"brasil", "brazil"}
            )
        )

        if is_country_level:
            # Código do Brasil no padrão IBGE para o layer nacional
            df["territory_code"] = 76

        # garantir tipo inteiro
        df["territory_code"] = pd.to_numeric(
            df["territory_code"], errors="raise"
        ).astype(int)
        return df

    # ---- Helpers de cache ---------------------------------------------------
    @classmethod
    def _normalize_key_part(cls, value: Any) -> Any:
        if value is None:
            return None
        from enum import Enum  # import local para evitar ciclo

        if isinstance(value, dict):
            return tuple(sorted(value.items()))
        if isinstance(value, list):
            return tuple(value)
        if isinstance(value, Enum):
            return value.value
        return value

    @classmethod
    def _make_cache_key(
        cls,
        *,
        culture: Culture,
        territorial_level: TerritorialLevel,
        classifications: dict[str, str] | None,
        variable: str | list[str] | None,
        period: int | str,
    ) -> tuple:
        return (
            ("culture", cls._normalize_key_part(culture)),
            ("territorial_level", cls._normalize_key_part(territorial_level)),
            ("classifications", cls._normalize_key_part(classifications)),
            ("variable", cls._normalize_key_part(variable)),
            ("period", cls._normalize_key_part(period)),
        )

    @classmethod
    def _cache_get(cls, key: tuple) -> pd.DataFrame | None:
        entry = cls._CACHE.get(key)
        if not entry:
            return None
        ts, df = entry
        if datetime.utcnow() - ts > cls._CACHE_TTL:
            cls._CACHE.pop(key, None)
            return None
        return df.copy(deep=True)

    @classmethod
    def _cache_set(cls, key: tuple, df: pd.DataFrame) -> None:
        cls._CACHE[key] = (datetime.utcnow(), df.copy(deep=True))
