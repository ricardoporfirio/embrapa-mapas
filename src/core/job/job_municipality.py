import os
from src.utils.atomic import save_csv, project_path
import json
from typing import Optional, Dict, Any

import pandas as pd  # apenas para contar linhas/valores existentes
from src.models.base_model import BaseModel
from src.core.sidra.base_downloader import _BaseSidraDownloader
from src.core.geobr_shapes.municipality import MunicipalityDownloader
from src.core.sidra.enums import TerritorialLevel, CultureStyle
from src.utils.merge_df_on_geojson import GeoMerger
from src.transforms.density import transform_density
from src.transforms.productivity import transform_productivity
from src.utils.create_folder import FolderCreator
from src.core.progress import ProgressMeta  # SSE opcional


def _emit(progress: Optional[ProgressMeta], payload: Dict[str, Any]) -> None:
    """Emite uma mensagem SSE (sem impactar barras globais)."""
    if not progress:
        return
    try:
        # usa a API interna do ProgressMeta (já serializa no sse.py como 'progress')
        progress._emit(payload)  # type: ignore[attr-defined]
    except Exception:
        try:
            progress.queue.put(json.dumps(payload, ensure_ascii=False))  # fallback
        except Exception:
            pass


def job_municipality(
    year: int,
    shape_year: int,
    dir_name: str,
    style_folder: str,
    culture_style: CultureStyle,
    model: BaseModel,
    downloader_mk: _BaseSidraDownloader,
    downloader_pr: _BaseSidraDownloader,
    is_density: bool = False,
    is_productivity: bool = False,
    progress: Optional[
        ProgressMeta
    ] = None,  # <- NOVO: para relatar quantidades via SSE
):
    """
    Gera o dataframe municipal e salva CSV. Com SSE, informa:
      - total de bases de municípios (linhas/municípios) conhecidas
      - quantas já existem em disco (se houver CSV anterior)
      - quantas faltam para download/geração
      - ao final, a quantidade efetivamente disponível/pendente
    """
    # caminho do CSV final (para inspecionar o que "já tem")
    path = os.path.join("dataframes", dir_name, style_folder, "municipality")
    file_to_save = project_path(os.path.join(path, f"municipality-{year}.csv"))

    # Se existir CSV anterior, relata o que JÁ TEM em disco
    if os.path.isfile(file_to_save):
        try:
            prev = pd.read_csv(file_to_save)
            prev_total = int(len(prev))
            prev_have = (
                int(prev["value"].notna().sum())
                if "value" in prev.columns
                else prev_total
            )
            _emit(
                progress,
                {
                    "phase": "bases",
                    "scope": "municipality",
                    "stage": "disk",
                    "year": year,
                    "total": prev_total,
                    "have": prev_have,
                    "missing": max(prev_total - prev_have, 0),
                    "path": file_to_save,
                },
            )
        except Exception as e:
            _emit(
                progress,
                {
                    "phase": "bases",
                    "scope": "municipality",
                    "stage": "disk_error",
                    "year": year,
                    "error": str(e),
                    "path": file_to_save,
                },
            )

    downloader = MunicipalityDownloader()

    # 1) Baixa shapes para saber o TOTAL de municípios previstos (base de referência)
    gdf = downloader.download(year=shape_year)
    total_munis = int(getattr(gdf, "shape", (0, 0))[0])
    _emit(
        progress,
        {
            "phase": "bases",
            "scope": "municipality",
            "stage": "shapes_total",
            "year": year,
            "total": total_munis,
            "have": 0,
            "missing": total_munis,
        },
    )

    # 2) Baixa dados (ordenha/produção) — aqui ainda não sabemos quantos terão valor
    data_downloader = (
        downloader_pr
        if culture_style in (CultureStyle.PRODUCTION, CultureStyle.DENSITY_PRODUCTION)
        else downloader_mk
    )
    df = data_downloader.download(
        territorial_level=TerritorialLevel.MUNICIPALITY, period=year
    )

    # 3) Produtividade (se solicitada) antes do merge
    if is_productivity:
        if downloader_pr is None:
            _emit(
                progress,
                {
                    "phase": "bases",
                    "scope": "municipality",
                    "stage": "productivity_error",
                    "year": year,
                    "error": "is_productivity=True requer 'downloader_pr' válido.",
                },
            )
            raise ValueError("is_productivity=True requer 'downloader_pr' válido.")
        pr_df = downloader_pr.download(
            territorial_level=TerritorialLevel.MUNICIPALITY, period=year
        )
        df = transform_productivity(df_milking=df, df_production=pr_df, multiplier=1000)

    # 4) Merge df + shapes para alinhar por município
    mgdf = GeoMerger().merge(df=df, gdf=gdf)

    # 5) Enriquecimento pelo modelo e transformações
    model.set_df(mgdf)
    mgdf = model.set_descriptions_on_dataframe(style=culture_style, as_attrs=False)

    if is_density:
        mgdf = transform_density(df=mgdf, multiplier=1000 if culture_style == CultureStyle.DENSITY_PRODUCTION else 1)

    # 6) Contagem efetiva de MUNICÍPIOS COM DADO (have) vs faltantes
    #    - total: quantidade de municípios no merge (ou nos shapes)
    #    - have: linhas com 'value' não-nulo
    total_final = int(len(mgdf)) if getattr(mgdf, "shape", None) else total_munis
    have_final = (
        int(mgdf["value"].notna().sum()) if "value" in mgdf.columns else total_final
    )
    missing_final = max(total_final - have_final, 0)

    _emit(
        progress,
        {
            "phase": "bases",
            "scope": "municipality",
            "stage": "computed",
            "year": year,
            "total": total_final,
            "have": have_final,
            "missing": missing_final,
        },
    )

    # 7) Salva CSV
    save_mgdf = mgdf
    if "geometry" in mgdf.columns:
        mgdf = mgdf.drop("geometry", axis=1)

    FolderCreator().create_folder(path=path)
    save_csv(mgdf, file_to_save)

    # 8) Após salvar, confirma em disco
    _emit(
        progress,
        {
            "phase": "bases",
            "scope": "municipality",
            "stage": "saved",
            "year": year,
            "total": total_final,
            "have": have_final,
            "missing": missing_final,
            "path": file_to_save,
        },
    )

    return save_mgdf
