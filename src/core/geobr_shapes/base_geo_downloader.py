"""Base abstrata para download de shapes via geobr, com cache em disco (7 dias)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Final

from src.utils.atomic import atomic_output
from src.core.progress import report_activity
from src.utils.network import configure_geobr_network
import time
import joblib
import geopandas as gpd


class BaseGeoDownloader(ABC):
    """Fluxo padrão:
    1) Verifica cache (arquivo .joblib)
    2) Se inválido/ausente, baixa via geobr (`_fetch`)
    3) Converte para EPSG:4326, pós-processa e salva no cache
    """

    # diretório de cache por módulo
    CACHE_DIR: Final[Path] = Path(__file__).resolve().parent / ".cache"
    CACHE_DIR.mkdir(exist_ok=True)

    # TTL do cache (7 dias)
    CACHE_TTL_SECONDS: Final[int] = 7 * 24 * 3600

    # nome lógico do recurso (usado no nome do arquivo)
    resource_name: str = "resource"  # sobrescrever nas filhas

    def download(self, year: int = 2022, simplified: bool = True) -> gpd.GeoDataFrame:
        # normaliza o ano conforme as regras solicitadas
        norm_year = self._normalize_year(year)
        report_activity(f"Preparando geometrias: {self.resource_name} — {norm_year}")

        cache_file = self._cache_path(norm_year, simplified)

        # cache válido?
        if cache_file.exists():
            mtime = cache_file.stat().st_mtime
            if (time.time() - mtime) < self.CACHE_TTL_SECONDS:
                try:
                    return joblib.load(cache_file)
                except Exception:
                    pass  # Cache inválido: prossegue com um novo download.

        # baixa do geobr com o ano normalizado
        configure_geobr_network()
        gdf = self._fetch(year=norm_year, simplified=simplified)

        if not isinstance(gdf, gpd.GeoDataFrame):
            raise RuntimeError(f"Falha ao obter {self.resource_name} via geobr.")

        # CRS -> WGS84
        if gdf.crs is None or gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(4326)

        # pós-processamento/seleção/renome
        gdf = self._postprocess(gdf)

        # salva cache
        with atomic_output(cache_file) as temporary:
            joblib.dump(gdf, temporary)
        return gdf

    # ---------------------- métodos a serem implementados ---------------------
    @abstractmethod
    def _fetch(self, *, year: int, simplified: bool) -> gpd.GeoDataFrame:
        """Chama a função geobr correta (read_*) e retorna um GeoDataFrame bruto."""
        ...

    @abstractmethod
    def _postprocess(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Seleciona/renomeia colunas e faz ajustes específicos do recurso."""
        ...

    # ---------------------- helpers internos ---------------------------------
    def _cache_path(self, year: int, simplified: bool) -> Path:
        suffix = "simp" if simplified else "full"
        fname = f"{self.resource_name}_{year}_{suffix}.joblib"
        return self.CACHE_DIR / fname

    def _normalize_year(self, year: int) -> int:
        """Aplica as regras de normalização de ano.
        2000–2009 -> 2000; 2010–2019 -> 2010; >=2020 -> 2020; caso contrário, mantém.
        """
        if 2000 <= year <= 2009:
            return 2000
        if 2010 <= year <= 2019:
            return 2010
        if year >= 2020:
            return 2020
        # abaixo de 2000: mantém (ajuste aqui se quiser outra política)
        return year
