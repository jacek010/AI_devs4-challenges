import base64
import requests
import workspace as ws
from config import AZURE_DEPLOYMENT
from openai import AzureOpenAI
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


def read_image_url(url: str, question: str = "") -> str:
    """
    Pobiera obraz z URL i odczytuje jego treść przez Azure OpenAI Vision.
    Obraz i wynik vision są cache'owane lokalnie.
    Podaj question jeśli szukasz konkretnej informacji w obrazku.
    """
    key_img    = ws.cache_key(url)
    key_vision = ws.cache_key(url, suffix=".vision.txt")

    # Zwróć z cache jeśli pytanie jest domyślne (bez konkretnego pytania)
    if not question:
        cached = ws.cache_read(key_vision)
        if cached:
            ws.log("READ_IMAGE (cache)", url)
            return cached

    # Pobierz obraz (lub z cache binarnego)
    img_bytes = ws.cache_read_bytes(key_img)
    if img_bytes is None:
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            img_bytes = resp.content
        except Exception as e:
            err = f"IMAGE_FETCH_ERROR: {e}"
            ws.log("READ_IMAGE_ERROR", url, err)
            return err
        ws.cache_write(key_img, img_bytes)

    # Określ MIME type
    ext  = url.split(".")[-1].lower().split("?")[0]
    mime = {"png": "image/png", "jpg": "image/jpeg",
            "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")

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
            max_tokens=2000,
        )
        result = resp.choices[0].message.content
    except Exception as e:
        result = f"VISION_ERROR: {e}"

    ws.cache_write(key_vision, result)
    ws.log("READ_IMAGE", f"URL: {url}\nQuestion: {question}", result)
    return result


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_image_url",
            "description": (
                "Pobiera obraz z URL i odczytuje treść przez Vision AI. "
                "WYMAGANE dla plików .png/.jpg. Wyniki są cache'owane. "
                "Podaj question jeśli szukasz konkretnej informacji w obrazku."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "question": {"type": "string", "default": ""},
                },
                "required": ["url"],
            },
        },
    },
]
