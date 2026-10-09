import os
from src.utils.atomic import save_csv, project_path

from src.models.base_model import BaseModel
from src.core.sidra.base_downloader import _BaseSidraDownloader
from src.core.geobr_shapes.country import CountryDownloader
from src.core.sidra.enums import TerritorialLevel, CultureStyle
from src.utils.merge_df_on_geojson import GeoMerger
from src.transforms.density import transform_density
from src.transforms.productivity import transform_productivity
from src.utils.create_folder import FolderCreator


def job_country(
    year: int,
    shape_year: int,
    dir_name: str,
    style_folder: str,
    culture_style: CultureStyle,
    model: BaseModel,
    downloader_mk: _BaseSidraDownloader,
    downloader_pr: _BaseSidraDownloader,
    is_density=False,
    is_productivity=False,
):
    downloader = CountryDownloader()

    gdf = downloader.download(year=shape_year)
    data_downloader = (
        downloader_pr
        if culture_style in (CultureStyle.PRODUCTION, CultureStyle.DENSITY_PRODUCTION)
        else downloader_mk
    )
    df = data_downloader.download(territorial_level=TerritorialLevel.COUNTRY, period=year)

    if is_productivity:
        pr_df = downloader_pr.download(territorial_level=TerritorialLevel.COUNTRY, period=year)
        df = transform_productivity(df_milking=df, df_production=pr_df, multiplier=1000)

    mgdf = GeoMerger().merge(df=df, gdf=gdf)

    model.set_df(mgdf)
    mgdf = model.set_descriptions_on_dataframe(style=culture_style, as_attrs=False)

    if is_density:
        mgdf = transform_density(df=mgdf, multiplier=1000 if culture_style == CultureStyle.DENSITY_PRODUCTION else 1)

    if "geometry" in mgdf.columns:
        mgdf = mgdf.drop("geometry", axis=1)

    path = os.path.join("dataframes", dir_name, style_folder, "country")
    FolderCreator().create_folder(path=path)

    file_to_save = os.path.join(path, f"brasil-{year}.csv")
    save_csv(mgdf, file_to_save)
