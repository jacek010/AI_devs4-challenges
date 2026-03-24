"""
Rejestr wszystkich narzędzi agenta.

Aby dodać nowe narzędzie:
  1. Stwórz tools/moje_narzedzie.py z funkcją i DEFINITIONS = [...]
  2. Zaimportuj je tutaj i dodaj do _MODULES
  Gotowe — agent automatycznie je zobaczy.
"""

from tools import http, vision, hub, files, code, search

# ─── Lista modułów z narzędziami ──────────────────────────────
# Dodaj tu nowe moduły aby agent automatycznie je widział.
_MODULES = [http, vision, hub, files, code, search]

# ─── Budowanie rejestru ───────────────────────────────────────
TOOLS: list[dict]        = []
TOOL_MAP: dict[str, callable] = {}

for _mod in _MODULES:
    # Zbierz definicje JSON Schema dla OpenAI
    TOOLS.extend(_mod.DEFINITIONS)

    # Zbierz callable'e — nazwa funkcji → funkcja
    for _defn in _mod.DEFINITIONS:
        _name = _defn["function"]["name"]
        _fn   = getattr(_mod, _name, None)
        if _fn is None:
            raise AttributeError(
                f"Moduł {_mod.__name__} deklaruje '{_name}' w DEFINITIONS "
                f"ale nie eksportuje takiej funkcji."
            )
        TOOL_MAP[_name] = _fn
