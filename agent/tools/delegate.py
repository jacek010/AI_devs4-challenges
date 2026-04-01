"""
Narzędzia delegacji — główny agent używa ich do przekazywania podzadań
do wyspecjalizowanych subagentów.
"""

from subagents import vision as _vision_subagent


def delegate_vision_task(task: str) -> str:
    """
    Deleguje zadanie analizy wizualnej do wyspecjalizowanego vision subagenta.
    Subagent uruchamia własną, izolowaną pętlę i zwraca kompletny wynik.

    Subagent ma dostęp do: read_image, write_file, read_file,
    list_workspace, python_eval.
    """
    agent = _vision_subagent.create()
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
]
