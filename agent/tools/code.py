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
        "json":     json,
        "re":       __import__("re"),
        "math":     __import__("math"),
        "datetime": __import__("datetime"),
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
                "Wykonuje kod Python (obliczenia, formatowanie, parsowanie). "
                "Dostępne: json, re, math, datetime. Wyniki przez print()."
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
