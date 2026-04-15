import io
import json
import zipfile
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


def http_download_zip(url: str, extract_to: str = "", force_refresh: bool = False) -> str:
    """
    Pobiera plik .zip z URL, rozpakowuje go do folderu cache/<extract_to>/
    i zwraca listę wyodrębnionych plików wraz z ich ścieżkami w workspace.
    Jeśli extract_to jest puste, nazwa folderu pochodzi z nazwy pliku .zip.
    Wynik jest cache'owany — powtórne wywołanie zwróci istniejącą listę.
    """
    # Ustal nazwę folderu docelowego
    zip_name = url.split("?")[0].rstrip("/").split("/")[-1]
    folder_name = extract_to or zip_name.rsplit(".", 1)[0] or "zip_extracted"
    marker_key = f"{folder_name}/.extracted"

    if not force_refresh and ws.cache_read(marker_key) is not None:
        ws.log("HTTP_DOWNLOAD_ZIP (cache)", url)
    else:
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
        except Exception as e:
            err = f"HTTP_DOWNLOAD_ZIP_ERROR: {e}"
            ws.log("HTTP_DOWNLOAD_ZIP_ERROR", url, err)
            return err

        try:
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
        except zipfile.BadZipFile as e:
            err = f"HTTP_DOWNLOAD_ZIP_ERROR: Nieprawidłowy plik ZIP — {e}"
            ws.log("HTTP_DOWNLOAD_ZIP_ERROR", url, err)
            return err

        # Upewnij się, że folder docelowy istnieje przed rozpakowaniem
        (ws.root() / "cache" / folder_name).mkdir(parents=True, exist_ok=True)

        names = zf.namelist()
        file_names = []
        for name in names:
            if name.endswith("/"):
                # Wpis katalogowy — utwórz folder i pomiń
                (ws.root() / "cache" / folder_name / name).mkdir(parents=True, exist_ok=True)
                continue
            data = zf.read(name)
            dest = ws.root() / "cache" / folder_name / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data) if isinstance(data, bytes) else dest.write_text(data, encoding="utf-8")
            file_names.append(name)

        ws.cache_write(marker_key, "\n".join(file_names))
        ws.log("HTTP_DOWNLOAD_ZIP", url, f"Rozpakowano {len(file_names)} plików do cache/{folder_name}/")

    # Odczytaj listę plików z markera
    all_files = (ws.cache_read(marker_key) or "").splitlines()
    cache_dir = ws.root() / "cache" / folder_name

    _MAX_LISTING = 20
    if len(all_files) > _MAX_LISTING:
        shown = all_files[:_MAX_LISTING]
        listing = "\n".join(
            f"  {i + 1:>5}. cache/{folder_name}/{name}"
            for i, name in enumerate(shown)
        )
        listing += (
            f"\n  … ({len(all_files) - _MAX_LISTING} kolejnych plików pominięto"
            f" — łącznie {len(all_files)} plików."
            f" Użyj list_workspace() lub grep_workspace() aby eksplorować.)"
        )
    else:
        listing = "\n".join(
            f"  {i + 1:>5}. cache/{folder_name}/{name}"
            for i, name in enumerate(all_files)
        )
    summary = (
        f"Rozpakowano {len(all_files)} plików z {url}\n"
        f"Folder: {cache_dir}\n"
        f"Pliki:\n{listing}"
    )
    return summary


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
    {
        "type": "function",
        "function": {
            "name": "http_download_zip",
            "description": (
                "Pobiera plik .zip z URL i rozpakowuje go do folderu cache/<extract_to>/. "
                "Zwraca listę wyodrębnionych plików z ich ścieżkami w workspace. "
                "Wynik jest cache'owany — powtórne wywołanie nie pobiera ponownie. "
                "Użyj force_refresh=true aby wymusić ponowne pobranie."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Pełny URL do pliku .zip",
                    },
                    "extract_to": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Nazwa podfolderu w cache/ do którego trafią pliki. "
                            "Jeśli puste, użyta zostanie nazwa pliku .zip bez rozszerzenia."
                        ),
                    },
                    "force_refresh": {"type": "boolean", "default": False},
                },
                "required": ["url"],
            },
        },
    },
]
