import io
import json
import textwrap
import contextlib
import workspace as ws


def python_eval(code: str) -> str:
    """
    Wykonuje kod Pythona — obliczenia, formatowanie, parsowanie tekstu, operacje na plikach.
    Dostępne moduły: json, re, math, datetime, pathlib, glob, os. Wyniki przez print().
    Zmienna _workspace_root (Path) wskazuje na korzeń workspace — używaj jej do ścieżek.
    Funkcja write_file(filename, content) zapisuje plik do output/.
    """
    from tools.files import write_file as _write_file

    allowed = {
        "__builtins__": __builtins__,
        "json":         json,
        "re":           __import__("re"),
        "math":         __import__("math"),
        "datetime":     __import__("datetime"),
        "base64":       __import__("base64"),
        "collections":  __import__("collections"),
        "itertools":    __import__("itertools"),
        "hashlib":      __import__("hashlib"),
        "urllib":       __import__("urllib.parse"),
        "string":       __import__("string"),
        "decimal":      __import__("decimal"),
        "statistics":   __import__("statistics"),
        "pathlib":      __import__("pathlib"),
        "Path":         __import__("pathlib").Path,
        "glob":         __import__("glob"),
        "os":           __import__("os"),
        "_workspace_root": ws.root(),
        "write_file":   _write_file,
    }
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(textwrap.dedent(code), allowed)  # noqa: S102
        result = buf.getvalue() or "(brak outputu — użyj print())"
    except Exception as e:
        result = f"PYTHON_EVAL_ERROR: {e}"

    ws.log("PYTHON_EVAL", code[:200], result)
    return result


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "python_eval",
            "description": (
                "Wykonuje kod Python (obliczenia, formatowanie, parsowanie, kodowanie, operacje na plikach). "
                "Dostępne: json, re, math, datetime, base64, collections, itertools, "
                "hashlib, urllib.parse, string, decimal, statistics, pathlib, Path, glob, os. "
                "Zmienna _workspace_root (pathlib.Path) wskazuje na korzeń workspace — "
                "ZAWSZE używaj jej jako bazy ścieżek, np.: "
                "_workspace_root / 'cache' / 'sensors' / '0001.json'. "
                "Funkcja write_file(filename, content) zapisuje plik tekstowy do output/. "
                "Wyniki przez print()."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                },
                "required": ["code"],
            },
        },
    },
]
