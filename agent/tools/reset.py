"""
Narzędzie request_reset — pozwala agentowi poprosić o zresetowanie kontekstu.

Gdy agent utknął, wyczerpał pomysły lub wielokrotnie wysyłał błędne odpowiedzi,
może wywołać request_reset(reason=...). Runner.py wykryje sentinel, wygeneruje
podsumowanie sesji, zapyta użytkownika o akceptację i (po potwierdzeniu) zresetuje
listę messages, wstrzykując podsumowanie do nowego system prompt.
"""

# Specjalny ciąg wykrywany przez runner.py jako sygnał do resetu.
# Nie jest prawdziwą odpowiedzią narzędzia — to kanał sterujący pętlą.
RESET_SENTINEL = "__RESET_REQUESTED__"


def request_reset(reason: str) -> str:
    """
    Zgłasza prośbę o reset kontekstu.
    Runner.py wykrywa RESET_SENTINEL i obsługuje cały proces:
    generowanie podsumowania, pytanie użytkownika, restart pętli.
    """
    return f"{RESET_SENTINEL}:{reason}"


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "request_reset",
            "description": (
                "Prosi o zresetowanie całej konwersacji i rozpoczęcie zadania od początku. "
                "Użyj TYLKO gdy: (1) wielokrotnie wysyłałeś błędne odpowiedzi i nie wiesz jak je poprawić, "
                "(2) utknąłeś w pętli i wyczerpałeś wszystkie pomysły, "
                "(3) uzbierało się zbyt wiele sprzecznych założeń utrudniających myślenie. "
                "NIE używaj pochopnie — reset kasuje bieżący kontekst rozmowy. "
                "Przed restem ZAWSZE podaj konkretny powód (reason). "
                "Runner wygeneruje podsumowanie sesji, zapisze je na dysk, zapyta użytkownika "
                "o akceptację i — po potwierdzeniu — uruchomi nową pętlę z czystym kontekstem, "
                "wzbogaconym o wnioski z tej sesji."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": (
                            "Dlaczego prosisz o reset? Opisz konkretnie: "
                            "co próbowałeś, dlaczego to nie działało, czego nie rozumiesz. "
                            "Ten tekst trafi jako wstęp do podsumowania sesji."
                        ),
                    }
                },
                "required": ["reason"],
            },
        },
    }
]
