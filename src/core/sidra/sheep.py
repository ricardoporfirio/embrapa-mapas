from .base_downloader import _BaseSidraDownloader
from .enums import Culture


class SheepMilkingDownloader(_BaseSidraDownloader):
    """Ordenha de ovelhas"""

    @property
    def culture(self) -> Culture:
        return Culture.SHEEP_MILKING

    @property
    def variable(self):
        return "9537"

    @property
    def classifications(self):
        return None


class SheepProductionDownloader(_BaseSidraDownloader):
    """Produção de leite de ovelhas"""

    @property
    def culture(self) -> Culture:
        return Culture.SHEEP_PRODUCTION

    @property
    def variable(self):
        return "9538"

    @property
    def classifications(self):
        return None
