import re
import workspace as ws
import tiktoken

# ─── Regex do ekstrakcji z treści pliku ──────────────────────
# Zdjęcia Markdown: ![alt](url)
_MD_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)\)')
# Lokalne linki Markdown: [tekst](ścieżka) — bez https?:// i bez ![]()
_LOCAL_LINK_RE = re.compile(
    r'(?<!!)\[([^\]]+)\]\(((?!https?://)[^)]+\.[a-zA-Z0-9]{1,6})\)',
    re.IGNORECASE,
)


def _count_tokens(text: str) -> int:
    try:
        enc = tiktoken.get_encoding("o200k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


def _enrich_file_content(filename: str, content: str) -> str:
    """
    Wzbogaca treść pliku o:
    - nagłówek z atrybucją źródła (#9)
    - listę wykrytych obrazów Markdown (#10)
    - listę wykrytych lokalnych linków do dokumentów (#19)
    """
    all_lines = content.splitlines()
    total_lines = len(all_lines)
    total_tokens = _count_tokens(content)
    header = f"[PLIK: {filename} | {total_lines} linii | ~{total_tokens} tokenów]\n"

    output = header + content

    # Ekstrakcja obrazów Markdown (#10)
    images = _MD_IMAGE_RE.findall(content)
    if images:
        img_lines = "\n".join(
            f"  - [{alt or '(brak alt)'}]({url})" for alt, url in images
        )
        output += (
            f"\n\n<markdown_images>\n"
            f"Wykryto {len(images)} obraz(ów) — użyj delegate_vision_task aby przeanalizować:\n"
            f"{img_lines}\n"
            f"</markdown_images>"
        )

    # Wykrywanie lokalnych linków do dokumentów (#19)
    local_links = _LOCAL_LINK_RE.findall(content)
    # Ogranicz do 15 unikalnych ścieżek
    seen = set()
    unique_links = []
    for text, path in local_links:
        if path not in seen:
            seen.add(path)
            unique_links.append((text, path))
        if len(unique_links) >= 15:
            break
    if unique_links:
        link_lines = "\n".join(f"  - [{text}]({path})" for text, path in unique_links)
        output += (
            f"\n\n<related_documents>\n"
            f"Wykryto odnośniki do innych dokumentów — warto je zbadać:\n"
            f"{link_lines}\n"
            f"</related_documents>"
        )

    return output


def write_file(filename: str, content: str) -> str:
    """
    Zapisuje plik tekstowy do output/ w workspace.
    Używaj do zachowania deklaracji, wyników pośrednich przed wysłaniem.
    filename: sama nazwa pliku, np. 'declaration.txt'
    """
    path = ws.output_write(filename, content)
    ws.log("WRITE_FILE", f"output/{filename}", content)
    return f"Zapisano: {path}"


_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff", "svg"}


def read_file(filename: str) -> str:
    """
    Odczytuje wcześniej pobrany lub zapisany plik tekstowy z workspace.
    Przeszukuje output/ i cache/. Obsługuje częściowe dopasowanie nazwy.
    NIE służy do obrazów — do analizy PNG/JPG użyj delegate_vision_task.
    """
    # Wykryj pliki graficzne i od razu zwroć pomocny komunikat
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in _IMAGE_EXTENSIONS:
        return (
            f"IMAGE_FILE_ERROR: '{filename}' to plik graficzny — "
            "read_file() obsługuje wyłącznie pliki tekstowe. "
            "Aby pobrać i przeanalizować obraz użyj delegate_vision_task() "
            "podając URL obrazu oraz oczekiwany format wyniku."
        )
    result = ws.find_file(filename)
    if result:
        ws.log("READ_FILE", filename, result[:200])
        return _enrich_file_content(filename, result)
    return f"FILE_NOT_FOUND: '{filename}' — sprawdź list_workspace() aby zobaczyć dostępne pliki."


def list_workspace() -> str:
    """
    Listuje pliki w workspace (cache/ i output/).
    Sprawdź na początku pracy — agent może wznawiać przerwaną sesję.
    """
    result = ws.ls()
    ws.log("LIST_WORKSPACE", result)
    return result


def peek_file(filename: str, lines: int = 20) -> str:
    """
    Zwraca pierwsze N linii pliku bez ładowania całej treści.
    Przydatne do sprawdzenia nagłówków, struktury i języka dokumentu
    przed zdecydowaniem czy warto go w pełni odczytać.
    """
    lines = max(1, min(200, lines))
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in _IMAGE_EXTENSIONS:
        return (
            f"IMAGE_FILE_ERROR: '{filename}' to plik graficzny — "
            "peek_file() obsługuje wyłącznie pliki tekstowe."
        )
    content = ws.find_file(filename)
    if not content:
        return f"FILE_NOT_FOUND: '{filename}' — sprawdź list_workspace() aby zobaczyć dostępne pliki."

    all_lines = content.splitlines()
    total_lines = len(all_lines)
    total_tokens = _count_tokens(content)
    preview = "\n".join(all_lines[:lines])
    truncated = total_lines > lines
    header = (
        f"[PEEK: {filename} | {total_lines} linii | ~{total_tokens} tokenów"
        + (" | (pokazano pierwsze " + str(lines) + " linii)" if truncated else "")
        + "]\n"
    )
    ws.log("PEEK_FILE", filename, preview[:200])
    output = header + preview

    # Ekstrakcja obrazów i linków z podglądu (#10, #19)
    images = _MD_IMAGE_RE.findall(preview)
    if images:
        img_lines = "\n".join(
            f"  - [{alt or '(brak alt)'}]({url})" for alt, url in images
        )
        output += (
            f"\n\n<markdown_images>\n"
            f"Wykryto {len(images)} obraz(ów) w podglądzie:\n"
            f"{img_lines}\n"
            f"</markdown_images>"
        )
    local_links = _LOCAL_LINK_RE.findall(preview)
    if local_links:
        seen = set()
        unique = [(t, p) for t, p in local_links if p not in seen and not seen.add(p)][:10]
        link_lines = "\n".join(f"  - [{t}]({p})" for t, p in unique)
        output += (
            f"\n\n<related_documents>\n"
            f"Wykryto lokalne odnośniki:\n"
            f"{link_lines}\n"
            f"</related_documents>"
        )
    return output


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Zapisuje plik tekstowy do output/ w workspace. "
                "Używaj do zachowania deklaracji i wyników pośrednich."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Odczytuje plik z workspace (output/ lub cache/). "
                "Obsługuje częściowe dopasowanie nazwy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_workspace",
            "description": (
                "Listuje pliki w workspace. "
                "Zawsze wywołaj na początku — część plików może być z poprzedniej sesji."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "peek_file",
            "description": (
                "Zwraca pierwsze N linii pliku (domyślnie 20) wraz z informacją o rozmiarze. "
                "Używaj do skanowania nagłówków i struktury dokumentów bez ładowania całej treści. "
                "Pozwala szybko ocenić język i zawartość pliku przed pełnym read_file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Nazwa pliku (obsługuje częściowe dopasowanie).",
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Liczba linii do zwrócenia (1-200, domyślnie 20).",
                    },
                },
                "required": ["filename"],
            },
        },
    },
]
