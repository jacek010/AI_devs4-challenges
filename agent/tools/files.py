import workspace as ws
import tiktoken


def _count_tokens(text: str) -> int:
    try:
        enc = tiktoken.get_encoding("o200k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


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
        ws.log("READ_FILE", filename, result)
        return result
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
    return header + preview


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
