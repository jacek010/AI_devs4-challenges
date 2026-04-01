"""
Vision Subagent — specjalista od analizy wizualnej obrazów.

Dostępne narzędzia:
  - read_image  (pobieranie i analiza obrazów przez Vision AI — URL lub lokalny plik)
  - split_image_grid, inne cv_tools (operacje OpenCV na obrazach)
  - write_file      (zapis wyników do workspace)
  - read_file       (odczyt plików z workspace)
  - list_workspace  (lista plików w workspace)
  - python_eval     (obliczenia i transformacje danych)

Subagent NIE ma dostępu do: submit_answer, http_get, http_post, search,
hub-owych narzędzi — działa wyłącznie jako helper analizy wizualnej.
"""

from subagents.base import SubagentRunner
from tools import vision as _vision_mod
from tools import cv_tools as _cv_tools_mod
from tools import files as _files_mod
from tools import code as _code_mod

# ─── Prompt systemowy ─────────────────────────────────────────
VISION_SYSTEM_PROMPT = """\
Jesteś wyspecjalizowanym agentem analizy wizualnej. Twoim jedynym zadaniem jest
dokładna analiza obrazów i zwrócenie strukturalnych, kompletnych danych do
głównego agenta, który powierzył Ci to podzadanie.

STRATEGIA:
1. Na początku sprawdź list_workspace() — część obrazów może być już w cache.
2. Pobierz każdy wskazany obraz przez read_image.
   - Dla lokalnych plików z workspace (output/, cache/) podaj samą nazwę pliku, np. 'tile_1x1.png'.
   - Dla zdalnych URL podaj pełny adres http/https.
   - Dla chronionych endpointów Huba użyj authorize=true z samym endpointem (np. '/obraz.png').
   - ZAWSZE używaj no_cache=true gdy pobierasz obraz z Huba (authorize=true) lub gdy obraz
     przedstawia dynamiczny stan gry/planszy — inaczej dostaniesz stary, cache'owany wynik!
   - Jeśli szukasz konkretnej informacji, użyj parametru question.
3. Dla tabel i danych liczbowych przepisz dokładnie WSZYSTKIE wartości.
4. Gdy wyniki są złożone lub obszerne, użyj write_file do ich zachowania,
   a następnie wróć do nich przez read_file.
5. Używaj python_eval do przetwarzania i formatowania wyodrębnionych danych.
6. Zwróć głównemu agentowi pełen, ustrukturyzowany wynik — gotowy do użycia.

ZASADY:
- Twój wynik końcowy jest dosłownie tym, co główny agent dostanie jako odpowiedź.
  Musi być kompletny i precyzyjny.
- Nie próbuj zgadywać treści obrazu — jeśli coś jest nieczytelne, napisz to wprost.
- Nie wysyłaj żadnych odpowiedzi do Huba — Twoją rolą jest wyłącznie analiza.

ROZUMOWANIE (OBOWIĄZKOWE):
Przed każdym wywołaniem narzędzia napisz krótki blok:
  [DLACZEGO] <uzasadnienie — co wynika z poprzedniego kroku>
  [CO DALEJ] <konkretna akcja i jej cel>
"""

# ─── Budowanie zestawu narzędzi ───────────────────────────────
_MODULES = [_vision_mod, _cv_tools_mod, _files_mod, _code_mod]

_tool_definitions: list[dict] = []
_tool_map: dict = {}

for _mod in _MODULES:
    _tool_definitions.extend(_mod.DEFINITIONS)
    for _defn in _mod.DEFINITIONS:
        _name = _defn["function"]["name"]
        _fn = getattr(_mod, _name, None)
        if _fn is None:
            raise AttributeError(
                f"[vision subagent] Moduł {_mod.__name__} deklaruje '{_name}' "
                f"w DEFINITIONS ale nie eksportuje takiej funkcji."
            )
        _tool_map[_name] = _fn


# ─── Fabryka ─────────────────────────────────────────────────
def create(verbose: bool = True) -> SubagentRunner:
    """Tworzy i zwraca nową instancję Vision Subagenta."""
    return SubagentRunner(
        system_prompt=VISION_SYSTEM_PROMPT,
        tool_definitions=_tool_definitions,
        tool_map=_tool_map,
        name="vision",
        max_iterations=15,
        verbose=verbose,
    )
