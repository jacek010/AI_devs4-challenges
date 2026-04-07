import base64
import requests
import workspace as ws
from config import AZURE_DEPLOYMENT
from openai import AzureOpenAI
from pathlib import Path
import config

_client: AzureOpenAI | None = None


def _get_client() -> AzureOpenAI:
    global _client
    if _client is None:
        _client = AzureOpenAI(
            azure_endpoint=config.AZURE_ENDPOINT,
            api_key=config.AZURE_API_KEY,
            api_version=config.AZURE_API_VER,
        )
    return _client


_VALID_IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_IMAGE_MAGIC = {
    b"\x89PNG": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF8": "image/gif",
    b"RIFF": "image/webp",  # RIFF....WEBP
}


def _detect_mime(data: bytes) -> str | None:
    """Wykrywa MIME na podstawie magic bytes. Zwraca None jeśli nie rozpoznano."""
    for magic, mime in _IMAGE_MAGIC.items():
        if data[:len(magic)] == magic:
            return mime
    # dodatkowe sprawdzenie WEBP
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _is_valid_image_bytes(data: bytes) -> bool:
    return _detect_mime(data) is not None


def _load_local_image(filename: str) -> bytes | None:
    """Szuka pliku obrazu w output/ i cache/ workspace'u. Zwraca bytes lub None."""
    # Odetnij potencjalny prefix podkatalogu
    for prefix in ("output/", "cache/", "output\\", "cache\\"):
        if filename.startswith(prefix):
            filename = filename[len(prefix):]
            break
    for subdir in ("output", "cache"):
        path = ws.root() / subdir / filename
        if path.exists():
            return path.read_bytes()
    return None


def read_image(source: str, question: str = "", authorize: bool = False, no_cache: bool = False) -> str:
    """
    Zunifikowane narzędzie do analizy obrazów przez Vision AI.
    Działa zarówno z URL jak i z lokalnymi plikami w workspace.

    - Gdy source to URL (http/https) — pobiera obraz z sieci.
    - Gdy authorize=true — buduje URL jako {HUB_BASE_URL}/data/{HUB_API_KEY}{source}.
    - Gdy source to nazwa pliku (np. 'tile_1x1.png') — ładuje z output/ lub cache/.
    - Gdy no_cache=true — pomija cache i pobiera świeży obraz z sieci (użyj dla dynamicznych obrazów).

    Wyniki vision są cache'owane lokalnie.
    Podaj question jeśli szukasz konkretnej informacji w obrazku.
    """
    is_url = source.startswith("http://") or source.startswith("https://")

    if authorize:
        endpoint = source if source.startswith("/") else "/" + source
        source = f"{config.HUB_BASE_URL}/data/{config.HUB_API_KEY}{endpoint}"
        is_url = True
        no_cache = True  # obrazy z Huba są dynamiczne — zawsze pobieraj świeże

    # ── Lokalne pliki ──────────────────────────────────────────
    if not is_url:
        img_bytes = _load_local_image(source)
        if img_bytes is None:
            err = f"IMAGE_LOCAL_ERROR: Nie znaleziono pliku '{source}' w output/ ani cache/"
            ws.log("READ_IMAGE_ERROR", source, err)
            return err

        # Klucz cache dla vision na podstawie nazwy pliku (bez ścieżki)
        filename = Path(source).name
        key_vision = ws.cache_key(filename, suffix=".vision.txt")
        if not question and not no_cache:
            cached = ws.cache_read(key_vision)
            if cached:
                ws.log("READ_IMAGE (local cache)", source)
                return cached

        ext = filename.rsplit(".", 1)[-1].lower()
        mime = {"png": "image/png", "jpg": "image/jpeg",
                "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        prompt = question or (
            "Odczytaj dokładnie całą zawartość obrazu. "
            "Tabele przepisz jako tekst z wszystkimi wartościami. "
            "Nie pomijaj żadnych danych."
        )
        try:
            resp = _get_client().chat.completions.create(
                model=AZURE_DEPLOYMENT,
                messages=[{"role": "user", "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{img_b64}", "detail": "high"}},
                    {"type": "text", "text": prompt},
                ]}],
                max_completion_tokens=2000,
            )
            result = resp.choices[0].message.content
        except Exception as e:
            result = f"VISION_ERROR: {e}"

        ws.cache_write(key_vision, result)
        ws.log("READ_IMAGE", f"Local: {source}\nQuestion: {question}", result)
        return result

    # ── Zdalne URL ─────────────────────────────────────────────
    key_img    = ws.cache_key(source)
    key_vision = ws.cache_key(source, suffix=".vision.txt")

    if not question and not no_cache:
        cached = ws.cache_read(key_vision)
        if cached:
            ws.log("READ_IMAGE (cache)", source)
            return cached

    img_bytes = None if no_cache else ws.cache_read_bytes(key_img)
    if img_bytes is not None and not _is_valid_image_bytes(img_bytes):
        # Stary cache zawiera śmieciowe dane (np. odpowiedź błędu serwera) — usuń go
        ws.log("READ_IMAGE_CACHE_INVALID", source, f"Cache {key_img} nie jest obrazem ({len(img_bytes)} B) — pomijam")
        img_bytes = None

    if img_bytes is None:
        try:
            resp = requests.get(source, timeout=20)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if content_type and content_type not in _VALID_IMAGE_CONTENT_TYPES and not content_type.startswith("image/"):
                err = (
                    f"IMAGE_FETCH_ERROR: Serwer zwrócił Content-Type '{content_type}' zamiast obrazu. "
                    f"Treść odpowiedzi: {resp.text[:300]}"
                )
                ws.log("READ_IMAGE_ERROR", source, err)
                return err
            img_bytes = resp.content
            if not _is_valid_image_bytes(img_bytes):
                err = (
                    f"IMAGE_FETCH_ERROR: Pobrane dane nie są poprawnym obrazem "
                    f"({len(img_bytes)} B, Content-Type: {content_type}). "
                    f"Podgląd: {img_bytes[:80]!r}"
                )
                ws.log("READ_IMAGE_ERROR", source, err)
                return err
        except Exception as e:
            err = f"IMAGE_FETCH_ERROR: {e}"
            ws.log("READ_IMAGE_ERROR", source, err)
            return err
        ws.cache_write(key_img, img_bytes)

    mime = _detect_mime(img_bytes) or (
        {"png": "image/png", "jpg": "image/jpeg",
         "jpeg": "image/jpeg", "webp": "image/webp"}
        .get(source.split(".")[-1].lower().split("?")[0], "image/png")
    )
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    prompt  = question or (
        "Odczytaj dokładnie całą zawartość obrazu. "
        "Tabele przepisz jako tekst z wszystkimi wartościami. "
        "Nie pomijaj żadnych danych."
    )

    try:
        resp = _get_client().chat.completions.create(
            model=AZURE_DEPLOYMENT,
            messages=[{"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{img_b64}", "detail": "high"}},
                {"type": "text", "text": prompt},
            ]}],
            max_completion_tokens=2000,
        )
        result = resp.choices[0].message.content
    except Exception as e:
        result = f"VISION_ERROR: {e}"

    ws.cache_write(key_vision, result)
    ws.log("READ_IMAGE", f"URL: {source}\nQuestion: {question}", result)
    return result


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_image",
            "description": (
                "Zunifikowane narzędzie do analizy obrazów przez Vision AI. "
                "Gdy source to nazwa pliku (np. 'tile_1x1.png') — wczytuje lokalny plik z output/ lub cache/. "
                "Gdy source to URL (http/https) — pobiera obraz z sieci. "
                "Gdy authorize=true — sam endpoint (np. /obraz.png) jest rozwijany do pełnego URL z kluczem API. "
                "Wyniki są cache'owane. Podaj question aby zadać konkretne pytanie o obraz."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": (
                            "URL obrazu (http/https), nazwa lokalnego pliku (np. 'tile_1x1.png') "
                            "lub endpoint (np. '/obraz.png') gdy authorize=true"
                        ),
                    },
                    "question": {"type": "string", "default": ""},
                    "authorize": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Gdy true, buduje URL jako {HUB_BASE_URL}/data/{HUB_API_KEY}{source}. "
                            "Użyj gdy obraz jest pod endpointem wymagającym klucza API."
                        ),
                    },
                    "no_cache": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Gdy true, pomija lokalny cache i pobiera świeży obraz z sieci. "
                            "ZAWSZE używaj gdy chcesz sprawdzić aktualny stan dynamicznego obrazu "
                            "(np. planszy electricity po wykonaniu obrotów)."
                        ),
                    },
                },
                "required": ["source"],
            },
        },
    },
]
