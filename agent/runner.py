import json
import re
import datetime
import tiktoken
from openai import AzureOpenAI
import config
import workspace as ws
from prompts import SYSTEM_PROMPT
from tools import TOOLS, TOOL_MAP
from tools.reset import RESET_SENTINEL

_FLG_RE = re.compile(r'\{FLG:[^}]+\}')


def _is_hub_success(result: str) -> bool:
    """Sprawdza czy odpowiedź Huba zawiera kod 0 (sukces)."""
    try:
        data = json.loads(result)
        return int(data.get("code", -1)) == 0
    except Exception:
        return False



def _detect_flags(text: str, source: str, log) -> None:
    """Wykrywa wzorce {FLG:...} w tekście i zapisuje je do output/flags.txt."""
    found = _FLG_RE.findall(text)
    if not found:
        return
    flags_file = ws.root() / "output" / "flags.txt"
    with flags_file.open("a", encoding="utf-8") as f:
        for flag in found:
            f.write(f"{flag}  # źródło: {source}\n")
    for flag in found:
        log(f"\n\033[1;33m{'═' * 55}\033[0m")
        log(f"\033[1;33m  🚩 FLAGA WYKRYTA: {flag}\033[0m")
        log(f"\033[1;33m     Źródło: {source}\033[0m")
        log(f"\033[1;33m     Zapisano do: output/flags.txt\033[0m")
        log(f"\033[1;33m{'═' * 55}\033[0m")
    ws.log("FLAG_DETECTED", f"Źródło: {source}  |  Flagi: {', '.join(found)}")

# ─── Kolory ANSI ──────────────────────────────────────────────
_R  = "\033[0m"       # reset
_B  = "\033[1m"       # bold
_CY = "\033[1;36m"    # bold cyan   — nagłówki iteracji
_YL = "\033[1;33m"    # bold yellow — decyzja / reasoning agenta
_MG = "\033[1;35m"    # bold magenta— wywołanie narzędzia
_GR = "\033[1;32m"    # bold green  — odpowiedź systemu / wynik
_BL = "\033[1;34m"    # bold blue   — sleep
_RE = "\033[1;31m"    # bold red    — błędy


def _msg_has_tool_calls(msg) -> bool:
    """Sprawdza czy wiadomość (dict lub obiekt SDK) ma nieudzielone tool_calls."""
    if isinstance(msg, dict):
        return bool(msg.get("tool_calls"))
    return bool(getattr(msg, "tool_calls", None))


# ─── Pomocniki kompresji ──────────────────────────────────────

def _get_tiktoken_enc():
    try:
        return tiktoken.encoding_for_model(config.AZURE_DEPLOYMENT)
    except KeyError:
        return tiktoken.get_encoding("o200k_base")


def _msg_role(msg) -> str:
    if isinstance(msg, dict):
        return msg.get("role", "")
    return getattr(msg, "role", "")


def _msg_content_str(msg) -> str:
    """Serializuje content + tool_calls wiadomości do jednego stringa."""
    if isinstance(msg, dict):
        content = msg.get("content") or ""
        tcs = msg.get("tool_calls") or []
    else:
        content = getattr(msg, "content", "") or ""
        tcs = getattr(msg, "tool_calls", None) or []

    parts = [str(content)] if content else []
    for tc in tcs:
        if isinstance(tc, dict):
            fn = tc.get("function", {})
            parts.append(f"[tool_call: {fn.get('name', '?')}({fn.get('arguments', '')})]")
        else:
            fn = getattr(tc, "function", None)
            if fn:
                parts.append(f"[tool_call: {getattr(fn, 'name', '?')}({getattr(fn, 'arguments', '')})]")
    return "\n".join(parts)


def _count_history_tokens(messages: list) -> int:
    """Szacuje łączną liczbę tokenów całej historii (standard OpenAI: 4 overhead/msg)."""
    enc = _get_tiktoken_enc()
    total = 0
    for msg in messages:
        total += 4 + len(enc.encode(_msg_content_str(msg)))
    return total


def _compress_history(client, messages: list, compress_count: int, log) -> tuple[list, int]:
    """
    Zastępuje starszą część historii (wszystko poza _COMPRESS_KEEP_RECENT ostatnimi
    wiadomościami non-system) streszczeniem wygenerowanym przez LLM.
    Zachowuje pełną strukturę API (brak sierot role=tool).
    """
    system_msgs = [m for m in messages if _msg_role(m) == "system"]
    non_system  = [m for m in messages if _msg_role(m) != "system"]

    if len(non_system) <= config.COMPRESS_KEEP_RECENT:
        return messages, compress_count   # za mało wiadomości — nie kompresuj

    to_compress = non_system[:-config.COMPRESS_KEEP_RECENT]
    to_keep     = non_system[-config.COMPRESS_KEEP_RECENT:]

    # Usuń sieroty role=tool z początku to_keep (tool message musi mieć poprzednika assistant)
    while to_keep and _msg_role(to_keep[0]) not in ("user", "assistant"):
        to_keep.pop(0)

    compress_count += 1
    log(f"\n{_CY}{'─' * 55}{_R}")
    log(f"{_CY}  🗜  KOMPRESJA HISTORII #{compress_count} — streszczam {len(to_compress)} starszych wiad.{_R}")
    log(f"{_CY}{'─' * 55}{_R}")

    # Zbuduj narrację ze starych wiadomości (ogranicz content każdej do 3000 znaków)
    narrative_lines = []
    for m in to_compress:
        role    = _msg_role(m).upper()
        content = _msg_content_str(m)[:3000]
        narrative_lines.append(f"[{role}]: {content}")
    narrative = "\n\n".join(narrative_lines)

    compress_prompt = [
        {"role": "system", "content": (
            "Jesteś asystentem streszczającym historię rozmowy agenta AI. "
            "Twoje streszczenie zastąpi pełną historię, więc musi być kompletne i precyzyjne."
        )},
        {"role": "user", "content": (
            f"Poniżej znajduje się {len(to_compress)} wiadomości z historii agenta. "
            "Stwórz zwięzłe, FAKTOGRAFICZNE streszczenie w formacie Markdown, które zachowa "
            "wszystkie kluczowe informacje potrzebne do kontynuacji zadania.\n\n"
            "Uwzględnij obowiązkowo:\n"
            "1. **Co pobrano i przetworzono** — pliki, URL-e, dane z API\n"
            "2. **Podjęte działania i ich efekty** — co wywołano, co zwróciło\n"
            "3. **Kluczowe odpowiedzi systemu/Huba** — kody, komunikaty, odrzucone odpowiedzi\n"
            "4. **Ustalony stan wiedzy** — co wiadomo na pewno o zadaniu\n"
            "5. **Błędy i ślepe zaułki** — czego unikać\n"
            "6. **Aktualny stan** — gdzie jesteśmy, co pozostało do zrobienia\n\n"
            f"--- HISTORIA DO STRESZCZENIA ---\n{narrative}"
        )},
    ]

    def _do_compress_call(**extra) -> str | None:
        resp = client.chat.completions.create(
            model=config.AZURE_DEPLOYMENT,
            messages=compress_prompt,
            max_completion_tokens=3000,
            **extra,
        )
        choice = resp.choices[0]
        if choice.finish_reason != "stop":
            log(f"{_YL}  ⚠️  Kompresja: finish_reason={choice.finish_reason!r}{_R}")
        return choice.message.content

    try:
        summary_text = _do_compress_call(temperature=0.1)
    except Exception as e:
        log(f"{_RE}  ⚠️  Kompresja: błąd API ({e}), ponawiam bez temperature...{_R}")
        try:
            summary_text = _do_compress_call()
        except Exception as e2:
            log(f"{_RE}  ❌  Kompresja: nie udało się ({e2}) — historia nie zostanie skompresowana.{_R}")
            return messages, compress_count - 1

    if not summary_text:
        log(f"{_RE}  ❌  Kompresja: model zwrócił pustą treść — pomijam.{_R}")
        return messages, compress_count - 1

    filename = f"context_compression_{compress_count:02d}.md"
    ws.output_write(filename, summary_text)
    ws.log("CONTEXT_COMPRESSED", f"Kompresja #{compress_count} | zastąpiono {len(to_compress)} wiad. | plik: {filename}")
    log(f"{_GR}  ✅ Streszczenie zapisano: output/{filename}{_R}")

    summary_msg = {
        "role":    "user",
        "content": (
            f"[STRESZCZENIE HISTORII #{compress_count} — zastępuje {len(to_compress)} starszych wiadomości]\n\n"
            + summary_text
            + "\n\n[Koniec streszczenia — kontynuuj zadanie od tego punktu]"
        ),
    }

    new_messages = system_msgs + [summary_msg] + to_keep
    log(f"{_CY}  Historia: {len(messages)} → {len(new_messages)} wiad. "
        f"(~{_count_history_tokens(new_messages):,} tokenów){_R}")
    log(f"{_CY}{'─' * 55}{_R}\n")
    return new_messages, compress_count


def _generate_summary(client, messages: list, log) -> str:
    """
    Generuje LLM-owe podsumowanie bieżącej sesji do zapisania przed resetem.
    Wywołuje model BEZ narzędzi — zwykły completion.
    """
    log(f"\n{_CY}⏳ Generuję podsumowanie sesji przed resetem...{_R}")

    # API wymaga, żeby każda wiadomość asystenta z tool_calls była poprzedzona
    # odpowiedziami tool. W tym miejscu ostatnia wiadomość asystenta (z wywołaniem
    # request_reset) jeszcze nie ma odpowiedzi — usuwamy ją przed wysłaniem.
    # Historia jest już automatycznie streszczana przez _compress_history w pętli,
    # więc nie ma potrzeby dodatkowego przycinania.
    clean_messages = list(messages)
    while clean_messages and _msg_has_tool_calls(clean_messages[-1]):
        clean_messages.pop()

    summary_messages = clean_messages + [
        {
            "role": "user",
            "content": (
                "Wygeneruj szczegółowe podsumowanie tej sesji w formacie Markdown. "
                "Uwzględnij obowiązkowo:\n"
                "1. **Co pobrano i przetworzono** — lista plików, URL-i, danych\n"
                "2. **Wypróbowane podejścia** — co próbowałeś zrobić krok po kroku\n"
                "3. **Błędne odpowiedzi** — jakie odpowiedzi zostały odrzucone i dlaczego\n"
                "4. **Kluczowe błędy i wnioski** — co nie działało i czego unikać w następnej próbie\n"
                "5. **Stan workspace** — co jest w cache/ i output/ i czy warto to reużyć\n"
                "6. **Zalecenia dla następnej sesji** — konkretne wskazówki jak podejść do zadania od nowa\n\n"
                "Bądź precyzyjny i konkretny — to podsumowanie trafi jako kontekst do nowej sesji agenta."
            ),
        }
    ]

    def _do_call(**extra_kwargs) -> str | None:
        resp = client.chat.completions.create(
            model=config.AZURE_DEPLOYMENT,
            messages=summary_messages,
            max_completion_tokens=4000,
            **extra_kwargs,
        )
        choice = resp.choices[0]
        finish = choice.finish_reason
        content = choice.message.content
        if finish != "stop":
            log(f"{_YL}  ⚠️  Podsumowanie: finish_reason={finish!r}{_R}")
        if not content:
            log(f"{_RE}  ❌  Podsumowanie: model zwrócił pustą treść (finish_reason={finish!r}){_R}")
        return content

    try:
        content = _do_call(temperature=0.1)
    except Exception as e:
        # Reasoning models (o3, gpt-5.x) nie obsługują temperature != 1 — retry bez parametru
        log(f"\n{_RE}  ⚠️  Podsumowanie: błąd API ({e}), ponawiam bez temperature...{_R}")
        try:
            content = _do_call()
        except Exception as e2:
            log(f"\n{_RE}  ❌  Podsumowanie: nie udało się wygenerować ({e2}){_R}")
            return f"(błąd generowania podsumowania: {e2})"
    return content or "(brak podsumowania — model zwrócił pustą odpowiedź)"


def run(task_text: str, verbose: bool = True) -> str | None:
    """
    Główna pętla agenta. Przyjmuje treść zadania i wykonuje je do końca.
    Zwraca ostatnią wiadomość agenta.
    Obsługuje wielokrotne resety kontekstu po akceptacji użytkownika.
    """
    client = AzureOpenAI(
        azure_endpoint=config.AZURE_ENDPOINT,
        api_key=config.AZURE_API_KEY,
        api_version=config.AZURE_API_VER,
    )

    def log(*args, **kwargs):
        if verbose:
            print(*args, **kwargs)

    log(f"\n{_CY}🗂  Workspace : {ws.root()}/{_R}")
    log(f"{_CY}🤖 Model     : {config.AZURE_DEPLOYMENT}{_R}")
    log(f"{_CY}🔧 Narzędzia : {', '.join(TOOL_MAP.keys())}{_R}\n")

    reset_count    = 0
    compress_count = 0
    need_restart = True
    current_system_prompt = SYSTEM_PROMPT

    while need_restart:
        need_restart = False
        messages = [
            {"role": "system", "content": current_system_prompt},
            {
                "role": "user",
                "content": (
                    f"<context>\n"
                    f"  <date>{datetime.date.today().isoformat()}</date>\n"
                    f"  <workspace_files>{ws.ls()}</workspace_files>\n"
                    f"</context>\n"
                    f"<task>\n{task_text}\n</task>"
                ),
            },
        ]

        if reset_count > 0:
            log(f"\n{_CY}{'═' * 55}{_R}")
            log(f"{_CY}  🔄 RESTART #{reset_count} — nowy kontekst gotowy{_R}")
            log(f"{_CY}{'═' * 55}{_R}\n")

        reset_triggered = False  # ustawiane gdy reset potwierdzony (break z for-i)

        for i in range(1, config.MAX_ITERATIONS + 1):
            log(f"\n{_CY}{'═' * 55}{_R}")
            log(f"{_CY}  Iteracja {i} / {config.MAX_ITERATIONS}{_R}")
            log(f"{_CY}{'═' * 55}{_R}")

            # Automatyczna kompresja historii gdy zbliżamy się do limitu okna kontekstu
            tokens_now = _count_history_tokens(messages)
            if tokens_now > config.CONTEXT_WINDOW * config.COMPRESS_THRESHOLD:
                messages, compress_count = _compress_history(client, messages, compress_count, log)

            response = client.chat.completions.create(
                model=config.AZURE_DEPLOYMENT,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=config.LLM_TEMPERATURE,
                max_completion_tokens=config.LLM_MAX_TOKENS,
            )

            msg = response.choices[0].message
            messages.append(msg)

            if msg.content:
                has_tools = bool(msg.tool_calls)
                icon  = "🧠" if has_tools else "💬"
                label = f"Rozumowanie  (za chwilę: {len(msg.tool_calls)} wywołanie/a)" if has_tools else "Odpowiedź końcowa"
                log(f"\n{_YL}╔{'═' * 53}╗{_R}")
                log(f"{_YL}║  {icon}  {label}{_R}")
                log(f"{_YL}╚{'═' * 53}╝{_R}")
                for line in msg.content.splitlines():
                    log(f"{_YL}   {line}{_R}")
                _detect_flags(msg.content, f"agent/iter{i}", log)

            # Agent nie wywołał narzędzi — wymuś kontynuację
            if not msg.tool_calls:
                log(f"\n{_YL}{'─' * 55}{_R}")
                log(f"{_YL}  ⚠️  Brak wywołania narzędzia — wymuszam kontynuację.{_R}")
                log(f"{_YL}{'─' * 55}{_R}")
                messages.append({
                    "role":    "user",
                    "content": (
                        "Nie wywołałeś żadnego narzędzia. "
                        "Zadanie jest ukończone TYLKO gdy Hub zwróci kod 0. "
                        "Kontynuuj pracę i wywołaj odpowiednie narzędzie."
                    ),
                })
                continue

            # Wykonaj narzędzia
            for tc in msg.tool_calls:
                name  = tc.function.name
                args  = json.loads(tc.function.arguments)
                r_str = str(_call_tool(name, args, log))

                # Sukces od Huba — zakończ z kodem 0
                if name == "submit_answer" and _is_hub_success(r_str):
                    messages.append({
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "content":      r_str,
                    })
                    log(f"\n{_GR}{'═' * 55}{_R}")
                    log(f"{_GR}  🏆 Hub zwrócił kod 0 — zadanie zakończone sukcesem!{_R}")
                    log(f"{_GR}{'═' * 55}{_R}")
                    ws.log("SUCCESS", f"Hub zwrócił kod 0 | odpowiedź: {r_str[:300]}")
                    return msg.content

                if r_str.startswith(RESET_SENTINEL):
                    reset_count += 1
                    reason = args.get("reason", "(brak powodu)")
                    log(f"\n{_RE}{'═' * 55}{_R}")
                    log(f"{_RE}  🔄 PROŚBA O RESET #{reset_count}{_R}")
                    log(f"{_RE}  Powód: {reason}{_R}")
                    log(f"{_RE}{'═' * 55}{_R}")

                    summary = _generate_summary(client, messages, log)
                    summary_filename = f"reset_summary_{reset_count:02d}.md"
                    ws.output_write(summary_filename, summary)
                    ws.log(
                        "RESET_REQUESTED",
                        f"Reset #{reset_count} | Powód: {reason} | Podsumowanie: {summary_filename}",
                    )

                    log(f"\n{_YL}{'─' * 55}{_R}")
                    log(f"{_YL}  📋 Podsumowanie: output/{summary_filename}{_R}")
                    log(f"{_YL}{'─' * 55}{_R}")
                    preview_lines = summary.splitlines()
                    for line in preview_lines[:20]:
                        log(f"{_YL}  {line}{_R}")
                    if len(preview_lines) > 20:
                        log(f"{_YL}  …[podsumowanie skrócone w podglądzie]{_R}")
                    log(f"{_YL}{'─' * 55}{_R}")

                    log(f"\n{_B}Czy akceptujesz reset kontekstu? [t/n]: {_R}", end="")
                    answer = input().strip().lower()

                    if answer in ("t", "tak", "y", "yes"):
                        current_system_prompt = (
                            SYSTEM_PROMPT
                            + f"\n\n---\n## PODSUMOWANIE POPRZEDNIEJ SESJI (reset #{reset_count})\n\n"
                            + summary
                            + "\n---"
                        )
                        ws.log("RESET_CONFIRMED", f"Reset #{reset_count} zaakceptowany przez użytkownika")
                        log(f"\n{_GR}  ✅ Reset zaakceptowany. Startuje nowa sesja...{_R}\n")
                        need_restart = True
                        reset_triggered = True
                        break  # przerwij pętlę po tc — za chwilę break z for-i
                    else:
                        ws.log("RESET_CANCELLED", f"Reset #{reset_count} odrzucony przez użytkownika")
                        log(f"\n{_YL}  ↩️  Reset anulowany. Kontynuuję bieżącą sesję.{_R}\n")
                        messages.append({
                            "role":         "tool",
                            "tool_call_id": tc.id,
                            "content":      "Reset anulowany przez użytkownika. Kontynuuj zadanie dalej.",
                        })
                        # Bez break — przetwarzamy dalej pozostałe tool calls
                else:
                    messages.append({
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "content":      r_str,
                    })

            if reset_triggered:
                break  # wyjdź z pętli iteracji → while zrestartuje

        else:
            # for-i zakończył się normalnie (limit iteracji, bez resetu)
            log(f"\n{_RE}⚠️  Osiągnięto limit iteracji ({config.MAX_ITERATIONS}).{_R}")
            ws.log("LIMIT", f"Osiągnięto MAX_ITERATIONS={config.MAX_ITERATIONS}")
            return None

    return None


def _call_tool(name: str, args: dict, log) -> str:
    """Wywołuje narzędzie, loguje wywołanie i zwraca wynik jako string."""
    is_sleep = (name == "sleep")
    color = _BL if is_sleep else _MG

    log(f"\n{color}┌{'─' * 53}┐{_R}")
    log(f"{color}│  🔧 Narzędzie: {_B}{name}{_R}{color}(){_R}")
    for k, v in args.items():
        v_str = str(v)
        log(f"{color}│     {k}: {v_str}{_R}")
    log(f"{color}└{'─' * 53}┘{_R}")

    if is_sleep:
        secs = args.get("seconds", "?")
        log(f"{_BL}  ⏳ Czekam {secs}s...{_R}")

    fn = TOOL_MAP.get(name)
    if fn is None:
        result = f"UNKNOWN_TOOL: {name}"
    else:
        try:
            result = fn(**args)
        except Exception as e:
            result = f"TOOL_ERROR [{name}]: {e}"

    r_str = str(result)
    _detect_flags(r_str, f"tool/{name}", log)
    err   = r_str.startswith(("UNKNOWN_TOOL", "TOOL_ERROR", "HTTP_GET_ERROR", "HTTP_POST_ERROR"))
    res_color = _RE if err else _GR

    log(f"\n{res_color}┌{'─' * 53}┐{_R}")
    log(f"{res_color}│  📥 Odpowiedź systemu: {_B}{name}{_R}")
    # Wyświetl do 800 znaków z podziałem na linie
    display = r_str[:800] + ("…[skrócono]" if len(r_str) > 800 else "")
    for line in display.splitlines():
        log(f"{res_color}│  {line}{_R}")
    log(f"{res_color}└{'─' * 53}┘{_R}")

    return r_str
