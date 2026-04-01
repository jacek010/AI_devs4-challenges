import json
import requests
import workspace as ws
import config

_IMAGE_EXTENSIONS = {
    "png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff", "tif", "svg", "ico", "avif",
}


def _is_image_url(url: str) -> bool:
    """Sprawdza czy URL wskazuje na plik graficzny na podstawie rozszerzenia."""
    ext = url.split("?")[0].split(".")[-1].lower()
    return ext in _IMAGE_EXTENSIONS


def http_get(url: str, force_refresh: bool = False, authorize: bool = False) -> str:
    """
    Pobiera zasób tekstowy (MD, JSON, HTML, TXT) z URL.
    Wynik jest cache'owany — kolejne wywołania zwracają wersję z dysku.
    Użyj force_refresh=true tylko gdy potrzebujesz świeżych danych.
    Użyj authorize=true gdy endpoint /data/ wymaga klucza API —
    wtedy podaj sam endpoint (np. /plik.json), a pełny URL zostanie
    zbudowany jako {HUB_BASE_URL}/data/{HUB_API_KEY}{endpoint}.
    """
    if authorize:
        if not url.startswith("/"):
            url = "/" + url
        url = f"{config.HUB_BASE_URL}/data/{config.HUB_API_KEY}{url}"

    if _is_image_url(url):
        return (
            "HTTP_GET_ERROR: URL wskazuje na plik graficzny — użyj read_image() zamiast http_get(). "
            "http_get() służy wyłącznie do pobierania zasobów tekstowych (JSON, HTML, MD, TXT)."
        )

    key = ws.cache_key(url)

    if not force_refresh:
        cached = ws.cache_read(key)
        if cached:
            ws.log("HTTP_GET (cache)", url)
            return cached

    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        content = resp.text
    except Exception as e:
        err = f"HTTP_GET_ERROR: {e}"
        ws.log("HTTP_GET_ERROR", url, err)
        return err

    ws.cache_write(key, content)
    ws.log("HTTP_GET", url, content)
    return content


def http_post(url: str, payload: dict, save_as: str = "", authorize: bool = False) -> str:
    """
    Wysyła POST z payloadem JSON.
    Podaj save_as (nazwa pliku) aby zapisać odpowiedź do output/.
    Użyj authorize=true aby automatycznie wstrzyknąć apikey z konfiguracji do payloadu.
    """
    if authorize:
        payload = {"apikey": config.HUB_API_KEY, **payload}
    if _is_image_url(url):
        return (
            "HTTP_POST_ERROR: URL wskazuje na plik graficzny — użyj read_image() zamiast http_post(). "
            "http_post() służy wyłącznie do wysyłania żądań JSON."
        )

    try:
        resp = requests.post(url, json=payload, timeout=30)
        try:
            result = json.dumps(resp.json(), ensure_ascii=False, indent=2)
        except Exception:
            result = resp.text
    except Exception as e:
        result = f"HTTP_POST_ERROR: {e}"

    if save_as:
        ws.output_write(save_as, result)

    ws.log(
        "HTTP_POST",
        f"URL: {url}\nPayload: {json.dumps(payload, ensure_ascii=False)[:300]}",
        result,
    )
    return result


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "http_get",
            "description": (
                "Pobiera zasób tekstowy (MD, JSON, HTML) z URL. "
                "Wynik jest cache'owany — kolejne wywołania tego samego URL "
                "zwracają wersję z dysku bez ponownego pobierania. "
                "Użyj force_refresh=true tylko gdy potrzebujesz świeżych danych."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Pełny URL lub sam endpoint (np. /plik.json) gdy authorize=true",
                    },
                    "force_refresh": {"type": "boolean", "default": False},
                    "authorize": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Gdy true, traktuje url jako endpoint i buduje pełny URL: "
                            "{HUB_BASE_URL}/data/{HUB_API_KEY}{endpoint}"
                        ),
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_post",
            "description": (
                "Wysyła POST z JSON payloadem. "
                "Wynik można zapisać do output/ podając save_as. "
                "Użyj authorize=true aby automatycznie wstrzyknąć apikey do payloadu."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "payload": {"type": "object"},
                    "save_as": {
                        "type": "string",
                        "default": "",
                        "description": "Opcjonalna nazwa pliku w output/",
                    },
                    "authorize": {
                        "type": "boolean",
                        "default": False,
                        "description": "Gdy true, automatycznie dodaje apikey z konfiguracji do payloadu",
                    },
                },
                "required": ["url", "payload"],
            },
        },
    },
]
