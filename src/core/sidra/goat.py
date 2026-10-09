from .base_downloader import _BaseSidraDownloader
from .enums import Culture


class GoatMilkingDownloader(_BaseSidraDownloader):
    """Ordenha de cabras"""

    @property
    def culture(self) -> Culture:
        return Culture.GOAT_MILKING

    @property
    def variable(self):
        return "2215"

    @property
    def classifications(self):
        return None


class GoatProductionDownloader(_BaseSidraDownloader):
    """Produção de leite de cabras"""

    @property
    def culture(self) -> Culture:
        return Culture.GOAT_PRODUCTION

    @property
    def variable(self):
        return "2216"

    @property
    def classifications(self):
        return None
