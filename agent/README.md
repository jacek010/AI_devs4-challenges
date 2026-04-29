# Agent — dokumentacja i plan wdrożenia UI

## Uruchomienie

```bash
# Tryb terminalowy (jak dotychczas — backward compatible)
python agent s05e04.md
python agent -i s05e04.md      # tryb interaktywny

# Textual TUI (nowe)
python agent --ui
```

### Instalacja zależności (jeśli jeszcze nie zainstalowano)

```bash
pip install -r agent/requirements.txt
```

---

## Architektura

```
agent/
├── __main__.py        — punkt wejścia; --ui → TUI, inaczej → CLI
├── runner.py          — główna pętla agenta (run / run_in_thread)
├── io_interface.py    — abstrakcja I/O (TerminalIO / TextualIO / UIStream)
├── ui_app.py          — Textual TUI
├── config.py          — konfiguracja (model, limity tokenów)
├── workspace.py       — zarządzanie folderami sesji (tasks/<name>/)
├── prompts.py         — system prompt
├── requirements.txt
├── subagents/
│   ├── base.py        — SubagentRunner (izolowana pętla, własne wiadomości)
│   ├── text.py        — subagent do analizy plików tekstowych
│   ├── vision.py      — subagent do analizy obrazów
│   └── web.py         — subagent do pobierania stron / wyszukiwania
└── tools/
    ├── ask.py         — ask_user (pyta użytkownika, input() → io_interface)
    ├── plan.py        — propose_plan, complete_plan_step
    ├── hub.py         — submit_answer (POST do hub.ag3nts.org/verify)
    ├── reset.py       — request_reset
    ├── delegate.py    — delegate_task / delegate_vision_task
    ├── files.py       — write_file, read_file, list_workspace, peek_file
    ├── grep.py        — grep_workspace
    ├── http.py        — http_get, http_post, http_download_zip
    ├── code.py        — python_eval
    ├── search.py      — web_search
    ├── sleep.py       — sleep
    ├── logs.py        — filter_log_file
    ├── tokenizer.py   — count_tokens
    └── vision.py      — read_image
```

### Warstwa I/O (`io_interface.py`)

Wszystkie `input()` w agenta przechodzą przez `io_interface.prompt_user()`.
- **TerminalIO** — opakowuje `input()`, identyczne z zachowaniem sprzed refaktoru
- **TextualIO** — kolejka `log_queue` + `threading.Event`; wątek agenta blokuje się
  do czasu gdy użytkownik odpowie przez UI
- **UIStream** — podmiana `sys.stdout`; strippuje kody ANSI, wrzuca do `log_queue`

### Mechanizm Stop

| Akcja | Opis |
|---|---|
| **🛑 Stop** | `request_stop()` → flaga `stop_event`; agent sprawdza ją na początku każdej iteracji i kończy po bieżącym kroku |
| **⛔ Force Stop** | `request_force_stop()` → `force_stop_event`; odblokuje oczekujący `prompt_user()` przez rzucenie `AgentStoppedException`; `run_in_thread()` łapie ten wyjątek |

### Komunikacja wątek agenta ↔ UI

```
wątek agenta (runner.py)
    │  print() → UIStream.write() → strip ANSI → log_queue.put(line)
    │  prompt_user()              → log_queue.put("__INPUT_REQUIRED__:<typ>:<pytanie>")
    │                             → blokuje na input_event.wait()
    ▼
Textual timer (co 50ms)          drains log_queue
    │  zwykłe linie              → RichLog.write()
    │  __INPUT_REQUIRED__        → InputBar.show_prompt()
    │  __AGENT_DONE__            → _on_agent_done(stopped=False)
    │  __AGENT_STOPPED__         → _on_agent_done(stopped=True)
    ▼
Button("Wyślij") / Enter         → TextualIO.set_answer() → input_event.set()
```

---

## Layout TUI

```
┌── Header: "🤖 Agent UI"  hub.ag3nts.org ───────────────────────────┐
├── [Tryb interaktywny: ○/●]  [status]  [🛑 Stop]  [⛔ Force Stop] ───┤
├── SessionPanel (22 cols) ──┬── right-pane ───────────────────────── ┤
│  📁 Sesje                  │  TaskSetup (przed startem agenta):      │
│  ─────────────            │    Select: pliki .md z AI_devs4/        │
│  s05e04  [🗑]              │    TextArea: własny problem              │
│  s04e01  [🗑]              │    [▶ Start]  [▶ Start Interaktywny]    │
│  s03e04  [🗑]              │  RichLog (podczas pracy agenta):        │
│  ...                       │    scrollowalny log wszystkich kroków   │
│                            ├── InputBar (hidden/shown):              │
│                            │    [pytanie od agenta]                  │
│                            │    [________input________] [Wyślij ↵]  │
└────────────────────────────┴─────────────────────────────────────────┘
```

---

## Folder sesji (`tasks/<name>/`)

Każde zadanie tworzy folder:

```
tasks/s05e04/
├── task.md             — kopia treści zadania
├── history.md          — append-only log (event, timestamp, detail)
├── plan.md             — plan kroków z checkboxami
├── memory_journal.md   — cross-session Observational Memory
├── cache/              — pobrane zasoby HTTP
└── output/             — wyniki, flagi, streszczenia
```

Usunięcie sesji przez UI → `shutil.rmtree(tasks/<name>/)`.

---

## Plan wdrożenia — status

- [x] Faza 1: `io_interface.py` — TerminalIO, TextualIO, UIStream, AgentStoppedException
- [x] Faza 2: Modyfikacje `tools/ask.py`, `tools/plan.py` — `input()` → `io_interface.prompt_user()`
- [x] Faza 3: Modyfikacje `runner.py` — `input()` → `io_interface.prompt_user()`, sprawdzanie stop flag, `run_in_thread()`
- [x] Faza 4: `ui_app.py` — Textual TUI (layout, SessionPanel, TaskSetup, InputBar, threading, stop buttons)
- [x] Faza 5: `__main__.py` — `--ui` flag, `task_file` opcjonalny
- [x] Faza 6: `requirements.txt` — dodano `textual>=0.79.0`
- [x] Faza 7: `README.md` — ten plik

---

## Weryfikacja

1. `python agent s05e04.md` — identyczne z poprzednim zachowaniem (TerminalIO, brak zmian w UX)
2. `python agent -i s05e04.md` — tryb interaktywny w terminalu nadal działa
3. `python agent --ui` — Textual TUI startuje bez argumentu zadania
4. W TUI: dropdown z plikami .md → wybór → Start → kroki pojawiają się w RichLog
5. W TUI: "Własny problem..." → textarea → Start → agent uruchamia się z wpisanym tekstem
6. Switch "Interaktywny" → każdy krok wymaga potwierdzenia przez InputBar
7. `propose_plan` → InputBar z planem; Enter = akceptacja, tekst = feedback
8. `ask_user` → InputBar z pytaniem agenta
9. Reset kontekstu → InputBar z pytaniem t/n
10. 🛑 Stop → agent kończy bieżącą iterację i zatrzymuje się
11. ⛔ Force Stop → agent przerywa natychmiast (nawet podczas oczekiwania na input)
12. Usunięcie sesji 🗑 → potwierdzenie modalne → `tasks/<name>/` usunięty → lista odświeżona
