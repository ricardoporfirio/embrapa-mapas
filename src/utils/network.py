"""Consultas externas com espera limitada e tentativas informadas no progresso."""
import time
import requests
from src.core.progress import report_activity


class DownloadError(RuntimeError):
    """Mensagem de falha externa que pode ser exibida ao usuário."""


def get_response(url, *, label, session=None, timeout=(10, 60), attempts=2):
    client = session if session is not None else requests
    for attempt in range(1, attempts + 1):
        report_activity(f"{label} — tentativa {attempt}/{attempts}")
        try:
            response = client.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            retryable = isinstance(error, (requests.Timeout, requests.ConnectionError)) or status == 429 or (status is not None and status >= 500)
            if retryable and attempt < attempts:
                report_activity(f"{label}: sem resposta válida; preparando nova tentativa")
                time.sleep(1)
                continue
            reason = "tempo de espera excedido" if isinstance(error, requests.Timeout) else (f"HTTP {status}" if status else "falha de conexão")
            raise DownloadError(f"{label}: {reason}. Tente novamente em alguns minutos.") from error


def configure_geobr_network():
    # geobr 0.2.2 centraliza metadados e GPKGs nesta função, sem expor timeout.
    # O adaptador altera somente o transporte do geobr, preservando seus leitores.
    import geobr.utils
    geobr.utils.url_solver = geobr_url_solver


def geobr_url_solver(url):
    import geobr.utils
    from pathlib import PurePosixPath
    from urllib.parse import urlparse
    filename = PurePosixPath(urlparse(url).path).name
    candidates = [url] + [mirror + filename for mirror in geobr.utils.MIRRORS]
    for index, candidate in enumerate(dict.fromkeys(candidates), 1):
        try:
            return get_response(candidate, label=f"Geometria {filename} (fonte {index})", attempts=1)
        except DownloadError:
            continue
    raise DownloadError(f"Não foi possível baixar {filename} nas fontes do geobr. Verifique a conexão e tente novamente.")
