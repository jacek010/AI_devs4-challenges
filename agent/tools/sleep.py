import time
import workspace as ws


def sleep(seconds: int) -> str:
    """
    Wstrzymuje agenta na podaną liczbę sekund.
    Używaj gdy endpoint zwróci instrukcję, że należy poczekać
    (np. rate-limit, 'wait N seconds', 'try again in N seconds').
    """
    seconds = max(0, int(seconds))
    ws.log("SLEEP", f"Czekam {seconds}s na polecenie endpointu")
    time.sleep(seconds)
    return f"Odczekano {seconds} sekund. Można kontynuować."


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "sleep",
            "description": (
                "Wstrzymuje agenta na podaną liczbę sekund. "
                "Używaj gdy endpoint zwróci instrukcję czekania, np. "
                "'wait N seconds', 'retry after N seconds', 'rate limit — try again in N s'. "
                "Nie używaj profilaktycznie — tylko gdy odpowiedź systemu tego wymaga."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "integer",
                        "description": "Liczba sekund do odczekania (min. 1).",
                        "minimum": 1,
                    },
                },
                "required": ["seconds"],
            },
        },
    },
]
