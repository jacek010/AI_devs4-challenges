from datetime import datetime
import workspace as ws
import config
from tools.http import http_post


def submit_answer(task: str, answer) -> str:
    """
    Wysyła finalną odpowiedź do hub.ag3nts.org/verify.
    Wynik zapisywany do output/submit_<task>_<hhmmss>.json.
    Używaj gdy odpowiedź jest gotowa i kompletna.
    Jeśli Hub zwróci błąd — przeczytaj komunikat i popraw odpowiedź.
    """
    payload  = {"apikey": config.HUB_API_KEY, "task": task, "answer": answer}
    ts       = datetime.now().strftime("%H%M%S")
    save_as  = f"submit_{task}_{ts}.json"
    return http_post(config.HUB_VERIFY_URL, payload, save_as=save_as)


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "submit_answer",
            "description": (
                "Wysyła finalną odpowiedź do hub.ag3nts.org/verify. "
                "Używaj gdy odpowiedź jest kompletna. "
                "Jeśli Hub zwróci błąd — przeczytaj go i popraw odpowiedź."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Nazwa zadania, np. 'sendit'",
                    },
                    "answer": {
                        "description": "Odpowiedź — string, liczba lub obiekt JSON",
                    },
                },
                "required": ["task", "answer"],
            },
        },
    },
]
