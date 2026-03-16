import logging
import requests

logger = logging.getLogger(__name__)


def safe_get(url: str, timeout: int = 15, headers: dict | None = None) -> str:
    default_headers = {
        "User-Agent": "Mozilla/5.0 (OpenClawBot/2.0)"
    }
    if headers:
        default_headers.update(headers)

    response = requests.get(url, timeout=timeout, headers=default_headers)
    response.raise_for_status()
    return response.text
