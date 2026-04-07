# tools/ask.py
import workspace as ws

_ASK = "\033[1;36m"  # bold cyan
_R   = "\033[0m"


def ask_user(question: str) -> str:
    """
    Zadaje pytanie użytkownikowi i zwraca jego odpowiedź.
    Używaj gdy zadanie jest niejednoznaczne i nie możesz kontynuować bez wyjaśnienia.
    Nie używaj w kółko — maksymalnie jedno pytanie na etap pracy.
    """
    print(f"\n{_ASK}{'─' * 55}{_R}")
    print(f"{_ASK}  ❓ PYTANIE DO UŻYTKOWNIKA:{_R}")
    print(f"{_ASK}  {question}{_R}")
    print(f"{_ASK}{'─' * 55}{_R}")
    print(f"{_ASK}  Twoja odpowiedź: {_R}", end="")
    answer = input().strip()
    ws.log("ASK_USER", question[:200], answer[:200])
    return answer


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "Zadaje pytanie użytkownikowi i czeka na odpowiedź tekstową. "
                "Używaj tylko gdy zadanie jest niejednoznaczne i nie możesz kontynuować "
                "bez wyjaśnienia. Nie zastępuje własnego rozumowania — najpierw spróbuj "
                "samodzielnie, dopiero potem pytaj."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Konkretne, zwięzłe pytanie do użytkownika.",
                    },
                },
                "required": ["question"],
            },
        },
    }
]
