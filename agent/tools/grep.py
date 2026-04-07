# tools/grep.py
import re
import workspace as ws


def grep_workspace(pattern: str, scope: str = "both", max_results: int = 50) -> str:
    """
    Przeszukuje treść plików w workspace po wzorcu (regex lub tekst).
    scope: 'cache' | 'output' | 'both' (domyślnie)
    max_results: maksymalna liczba dopasowań (1-200)
    Zwraca pasujące linie z nazwą pliku i numerem linii.
    """
    max_results = max(1, min(200, max_results))
    root = ws.root()

    dirs = []
    if scope in ("cache", "both"):
        dirs.append(root / "cache")
    if scope in ("output", "both"):
        dirs.append(root / "output")

    # Kompiluj wzorzec — obsługujemy zarówno regex jak i plain text
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error:
        # Jeśli wzorzec jest niepoprawnym regex — traktuj jako plain text
        rx = re.compile(re.escape(pattern), re.IGNORECASE)

    _TEXT_EXTENSIONS = {
        "txt", "md", "json", "csv", "xml", "html", "htm",
        "yaml", "yml", "log", "py", "js", "ts", "sh", "sql",
        "ini", "cfg", "toml", "rst", "",
    }
    _BINARY_EXTENSIONS = {
        "png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff",
        "pdf", "zip", "gz", "tar", "pkl", "bin", "mp3", "mp4",
    }

    matches = []
    files_scanned = 0

    for d in dirs:
        if not d.exists():
            continue
        for filepath in sorted(d.iterdir()):
            if not filepath.is_file():
                continue
            ext = filepath.suffix.lstrip(".").lower()
            if ext in _BINARY_EXTENSIONS:
                continue

            try:
                text = filepath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            files_scanned += 1
            for lineno, line in enumerate(text.splitlines(), start=1):
                if rx.search(line):
                    rel = filepath.relative_to(root)
                    matches.append(f"{rel}:{lineno}: {line.strip()}")
                    if len(matches) >= max_results:
                        break
            if len(matches) >= max_results:
                break

    if not matches:
        result = (
            f"GREP: brak wyników dla wzorca {pattern!r} "
            f"(przeszukano {files_scanned} plik/ów w: {scope})"
        )
    else:
        header = (
            f"GREP: {len(matches)} wynik/ów dla {pattern!r} "
            f"(przeszukano {files_scanned} plik/ów)"
            + (" [LIMIT]" if len(matches) >= max_results else "")
        )
        result = header + "\n\n" + "\n".join(matches)

    ws.log("GREP_WORKSPACE", f"pattern={pattern!r} scope={scope}", result[:300])
    return result


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "grep_workspace",
            "description": (
                "Przeszukuje treść plików w workspace (cache/ i output/) po wzorcu tekstowym lub regex. "
                "Zwraca pasujące linie z nazwą pliku i numerem linii. "
                "Używaj do iteracyjnego odkrywania słów kluczowych, synonimów i powiązanych zagadnień "
                "bez konieczności czytania całych plików."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": (
                            "Wzorzec wyszukiwania (tekst lub regex, bez rozróżniania wielkości liter). "
                            "Przykład: 'klucz|hasło|token' lub 'https?://'"
                        ),
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["cache", "output", "both"],
                        "description": "Zakres wyszukiwania: 'cache', 'output' lub 'both' (domyślnie).",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maksymalna liczba dopasowań do zwrócenia (1-200, domyślnie 50).",
                    },
                },
                "required": ["pattern"],
            },
        },
    }
]
