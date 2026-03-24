import json
import requests
import workspace as ws


def http_get(url: str, force_refresh: bool = False) -> str:
    """
    Pobiera zasób tekstowy (MD, JSON, HTML, TXT) z URL.
    Wynik jest cache'owany — kolejne wywołania zwracają wersję z dysku.
    Użyj force_refresh=true tylko gdy potrzebujesz świeżych danych.
    """
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


def http_post(url: str, payload: dict, save_as: str = "") -> str:
    """
    Wysyła POST z payloadem JSON.
    Podaj save_as (nazwa pliku) aby zapisać odpowiedź do output/.
    """
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
                    "url": {"type": "string"},
                    "force_refresh": {"type": "boolean", "default": False},
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
                "Wynik można zapisać do output/ podając save_as."
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
                },
                "required": ["url", "payload"],
            },
        },
    },
]
