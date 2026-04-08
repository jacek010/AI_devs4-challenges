"""
Narzędzia delegacji — główny agent używa ich do przekazywania podzadań
do wyspecjalizowanych subagentów.
"""

from subagents import vision as _vision_subagent
from subagents import web as _web_subagent
from subagents import text as _text_subagent

_AGENT_REGISTRY = {
    "vision": _vision_subagent,
    "web":    _web_subagent,
    "text":   _text_subagent,
}


def delegate_vision_task(task: str) -> str:
    """
    Deleguje zadanie analizy wizualnej do wyspecjalizowanego vision subagenta.
    Subagent uruchamia własną, izolowaną pętlę i zwraca kompletny wynik.

    Subagent ma dostęp do: read_image, write_file, read_file,
    list_workspace, python_eval.
    """
    agent = _vision_subagent.create()
    return agent.run(task)


def delegate_task(agent_type: str, task: str) -> str:
    """
    Deleguje podzadanie do wyspecjalizowanego subagenta.

    agent_type:
      'web'  — pobieranie stron, wyszukiwanie w sieci (http_get, web_search)
      'text' — analiza plików workspace (read_file, grep_workspace, peek_file)

    ZASADA PRZED WYWOŁANIEM:
    Rozpisz w task: (1) kontekst zadania, (2) cel podzadania,
    (3) oczekiwany format wyniku, (4) dostępne zasoby (pliki, URL-e).
    Subagent widzi TYLKO to co podasz w 'task'.
    """
    mod = _AGENT_REGISTRY.get(agent_type)
    if mod is None:
        available = ", ".join(f"'{k}'" for k in _AGENT_REGISTRY)
        return f"DELEGATE_ERROR: nieznany typ agenta '{agent_type}'. Dostępne: {available}"
    agent = mod.create()
    return agent.run(task)


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "delegate_vision_task",
            "description": (
                "Deleguje zadanie do wyspecjalizowanego vision subagenta. "
                "Użyj gdy zadanie wymaga: odczytania obrazu, ekstrakcji danych "
                "ze screenshota/zdjęcia/tabeli, OCR, analizy wizualnej treści. "
                "Podaj w 'task' pełny opis zadania WRAZ z URL-ami obrazów i "
                "oczekiwanym formatem wyniku. "
                "Subagent zwraca ustrukturyzowane wyniki gotowe do dalszego użycia."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": (
                            "Pełny opis zadania dla vision subagenta. "
                            "Zawrzyj: co dokładnie przeanalizować, URL-e obrazów, "
                            "jakich danych szukasz, oczekiwany format wyniku."
                        ),
                    },
                },
                "required": ["task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_task",
            "description": (
                "Deleguje podzadanie do wyspecjalizowanego subagenta. "
                "Typy: 'web' (pobieranie stron, wyszukiwanie w sieci), "
                "'text' (analiza plików workspace, grep). "
                "Użyj gdy zadanie wymaga intensywnego przeszukiwania lub przetwarzania "
                "i chcesz izolować ten etap od głównego kontekstu. "
                "PRZED UżYCIEM w parametrze 'task' rozpisz: (1) kontekst zadania, "
                "(2) cel podzadania, (3) oczekiwany format wyniku, "
                "(4) dostępne zasoby. Subagent widzi TYLKO to co podasz w 'task'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_type": {
                        "type": "string",
                        "enum": ["web", "text"],
                        "description": "Typ subagenta: 'web' (sieć) lub 'text' (pliki workspace).",
                    },
                    "task": {
                        "type": "string",
                        "description": (
                            "Pełny opis zadania dla subagenta — self-contained. "
                            "Zawrzyj: cel, zasoby (URL-e / nazwy plików), "
                            "czego szukać, oczekiwany format wyniku."
                        ),
                    },
                },
                "required": ["agent_type", "task"],
            },
        },
    },
]
