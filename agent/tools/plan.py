# tools/plan.py
import re
import workspace as ws

_CY = "\033[1;36m"   # bold cyan
_BL = "\033[1;34m"   # bold blue
_GR = "\033[1;32m"   # bold green
_YL = "\033[1;33m"   # bold yellow
_RE = "\033[1;31m"   # bold red
_R  = "\033[0m"

_ACCEPT_TOKENS = {"", "tak", "yes", "ok", "akceptuję", "akceptuje", "accept", "y"}

# Wzorzec kroku z checkboxem: "- [ ] 1." lub "- [ ] 1:"
_STEP_RE = re.compile(r'^(\s*-\s*\[[ xX]\]\s*)(\d+)[.:]', re.MULTILINE)


def propose_plan(plan: str) -> str:
    """
    Prezentuje użytkownikowi proponowany plan działania (listę kroków TODO),
    zapisuje go do pliku plan.md w workspace i czeka na akceptację lub pytania.

    WYMAGANY FORMAT PLANU — każdy krok jako checkbox Markdown:
      - [ ] 1. Opis kroku (narzędzie, cel, oczekiwany wynik)
      - [ ] 2. Opis kolejnego kroku
      ...

    Zwraca "ACCEPTED" gdy użytkownik zaakceptował plan.
    Gdy użytkownik wpisze pytania lub uwagi — zwraca ich treść, abyś mógł
    poprawić plan i wywołać propose_plan ponownie ze zaktualizowaną wersją.
    """
    # Zapisz plan do pliku (nadpisuje poprzednią wersję przy rewizji)
    plan_file = ws.root() / "plan.md"
    plan_file.write_text(plan, encoding="utf-8")
    ws.log("PLAN_PROPOSED", plan[:300])

    # Prezentacja w terminalu
    print(f"\n{_CY}{'═' * 55}{_R}")
    print(f"{_CY}  📋  PLAN DZIAŁANIA{_R}")
    print(f"{_CY}{'═' * 55}{_R}")
    for line in plan.splitlines():
        print(f"{_BL}  {line}{_R}")
    print(f"{_CY}{'═' * 55}{_R}")
    print(f"{_YL}  Plan zapisano do: {plan_file}{_R}")
    print(f"{_CY}{'─' * 55}{_R}")
    print(f"{_GR}  Zaakceptuj plan wciskając ENTER lub wpisz 'tak'/'ok'.{_R}")
    print(f"{_GR}  Aby zadać pytanie lub dodać uwagi — wpisz je poniżej.{_R}")
    print(f"{_CY}{'─' * 55}{_R}")
    print(f"{_CY}  Twoja odpowiedź: {_R}", end="")

    answer = input().strip()
    answer_lower = answer.lower()

    if answer_lower in _ACCEPT_TOKENS:
        ws.log("PLAN_ACCEPTED", "Użytkownik zaakceptował plan")
        print(f"\n{_GR}  ✅ Plan zaakceptowany — przechodzę do implementacji.{_R}\n")
        return "ACCEPTED"
    else:
        ws.log("PLAN_FEEDBACK", answer[:300])
        print(f"\n{_YL}  💬 Uwagi przyjęte — aktualizuję plan.{_R}\n")
        return answer


def complete_plan_step(step_number: int, notes: str = "") -> str:
    """
    Oznacza krok planu jako ukończony w pliku plan.md.
    Zmienia '- [ ] N.' na '- [x] N.' i opcjonalnie dopisuje wnioski pod krokiem.
    Wywołuj NATYCHMIAST po zakończeniu każdego kroku planu, przed przejściem
    do następnego.
    """
    plan_file = ws.root() / "plan.md"
    if not plan_file.exists():
        return f"BŁĄD: Plik plan.md nie istnieje w workspace ({plan_file})."

    content = plan_file.read_text(encoding="utf-8")
    lines   = content.splitlines(keepends=True)

    # Szukaj linii z - [ ] {step_number}. lub - [ ] {step_number}:
    step_pat = re.compile(
        r'^(\s*-\s*)\[\s\](\s*' + str(step_number) + r'[.:])',
        re.IGNORECASE,
    )
    found_idx = None
    for idx, line in enumerate(lines):
        if step_pat.match(line):
            found_idx = idx
            break

    if found_idx is None:
        # Może już oznaczony lub nie istnieje
        already_done = re.compile(
            r'^\s*-\s*\[[xX]\]\s*' + str(step_number) + r'[.:]',
        )
        if any(already_done.match(l) for l in lines):
            return f"Krok {step_number} był już oznaczony jako ukończony."
        return (
            f"BŁĄD: Nie znaleziono kroku {step_number} w plan.md. "
            "Upewnij się, że plan używa formatu '- [ ] N. Opis'."
        )

    # Zamień [ ] na [x]
    lines[found_idx] = step_pat.sub(r'\1[x]\2', lines[found_idx])

    # Wstaw wnioski bezpośrednio po linii kroku
    if notes:
        note_lines = [f"  > 📝 {note_line}\n" for note_line in notes.splitlines()]
        lines[found_idx + 1 : found_idx + 1] = note_lines

    plan_file.write_text("".join(lines), encoding="utf-8")
    ws.log("PLAN_STEP_DONE", f"Krok {step_number} ukończony" + (f" | {notes[:150]}" if notes else ""))

    # Wyświetl postęp
    total  = len(_STEP_RE.findall("".join(lines)))
    done   = sum(1 for l in lines if re.match(r'^\s*-\s*\[[xX]\]', l))
    print(f"\n{_GR}{'─' * 55}{_R}")
    print(f"{_GR}  ✅  Krok {step_number} — UKOŃCZONY  [{done}/{total}]{_R}")
    if notes:
        for note_line in notes.splitlines():
            print(f"{_YL}     📝 {note_line}{_R}")
    print(f"{_GR}{'─' * 55}{_R}\n")

    return f"Krok {step_number} oznaczony jako ukończony. Postęp: {done}/{total} kroków."


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "propose_plan",
            "description": (
                "Prezentuje użytkownikowi proponowany plan działania i zapisuje go do pliku "
                "plan.md w workspace. Czeka na akceptację lub pytania. "
                "Zwraca 'ACCEPTED' gdy plan zaakceptowany, lub treść uwag użytkownika gdy "
                "plan wymaga poprawy — popraw plan i wywołaj propose_plan ponownie. "
                "Wywołuj ZAWSZE po zrozumieniu zadania, PRZED pierwszym krokiem implementacyjnym. "
                "WYMAGANY FORMAT planu: każdy krok jako checkbox Markdown, np.:\n"
                "- [ ] 1. Pobierz dane przez http_get (oczekiwany wynik: JSON z listą)\n"
                "- [ ] 2. Przetwórz przez python_eval\n"
                "- [ ] 3. Wyślij przez submit_answer"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plan": {
                        "type": "string",
                        "description": (
                            "Szczegółowy plan działania w formacie Markdown. "
                            "KAŻDY krok MUSI być w formacie checkboxa: "
                            "'- [ ] N. Opis kroku (narzędzie, cel, oczekiwany wynik)'. "
                            "Kroki numerowane od 1. Bez tego formatu complete_plan_step nie zadziała."
                        ),
                    }
                },
                "required": ["plan"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_plan_step",
            "description": (
                "Oznacza krok planu jako ukończony w pliku plan.md (zmienia '- [ ]' na '- [x]') "
                "i opcjonalnie dopisuje wnioski/obserwacje pod krokiem. "
                "Wywołuj NATYCHMIAST po zakończeniu każdego kroku planu, przed przejściem "
                "do następnego. Dzięki temu plan.md odzwierciedla aktualny postęp."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "step_number": {
                        "type": "integer",
                        "description": "Numer kroku do oznaczenia jako ukończony (zgodny z numeracją w plan.md).",
                    },
                    "notes": {
                        "type": "string",
                        "description": (
                            "Opcjonalne wnioski, obserwacje lub wyniki uzyskane po realizacji kroku. "
                            "Zostaną dopisane pod krokiem w plan.md. Wpisz co znalazłeś, "
                            "co zwróciło narzędzie, jakie podjąłeś decyzje."
                        ),
                    },
                },
                "required": ["step_number"],
            },
        },
    },
]
