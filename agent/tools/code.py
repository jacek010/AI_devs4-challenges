import io
import json
import textwrap
import contextlib
import workspace as ws


def python_eval(code: str) -> str:
    """
    Wykonuje kod Pythona — obliczenia, formatowanie, parsowanie tekstu.
    Dostępne moduły: json, re, math, datetime. Wyniki przez print().
    """
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
                "Wykonuje kod Python (obliczenia, formatowanie, parsowanie, kodowanie). "
                "Dostępne: json, re, math, datetime, base64, collections, itertools, "
                "hashlib, urllib.parse, string, decimal, statistics. Wyniki przez print()."
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
