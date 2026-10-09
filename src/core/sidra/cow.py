from .base_downloader import _BaseSidraDownloader
from .enums import Culture


class CowMilkingDownloader(_BaseSidraDownloader):
    """Ordenha de vacas"""

    @property
    def culture(self) -> Culture:
        return Culture.COW_MILKING

    @property
    def variable(self):
        return None

    @property
    def classifications(self):
        return None


class CowProductionDownloader(_BaseSidraDownloader):
    """Produção de leite de vaca"""

    @property
    def culture(self) -> Culture:
        return Culture.COW_PRODUCTION

    @property
    def variable(self):
        return "106"

    @property
    def classifications(self):
        return {"80": "2682"}  # filtro 80/2682
