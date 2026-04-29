"""
ui_app.py — Textual TUI dla agenta zadaniowego.

Uruchomienie:
    python agent --ui

Layout:
  ┌── Header: "🤖 Agent UI"  [Interactive ○/●]  [🛑 Stop] [⛔ Force Stop] ─┐
  ├── SessionPanel (20%) ──┬── MainArea (80%) ─────────────────────────────┤
  │  Sesje (tasks/)        │  [TaskSetup] ← widoczny gdy agent nie działa  │
  │  ─────────────         │    Select: .md z AI_devs4/                    │
  │  s05e04  [🗑]           │    TextArea: własny problem                   │
  │  s04e01  [🗑]           │    [▶ Start] [▶ Start Interaktywny]           │
  │                        │  [StepLog]  ← RichLog podczas pracy agenta    │
  │                        ├── InputBar (ukryty/widoczny) ─────────────────│
  │                        │  [Pytanie agenta]                              │
  │                        │  [____ input ____] [Wyślij]                   │
  └────────────────────────┴────────────────────────────────────────────────┘
"""
from __future__ import annotations

import shutil
import sys
import threading
from pathlib import Path

import workspace as ws
import runner as agent_runner
import io_interface as ioi

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Select,
    Static,
    Switch,
    TextArea,
)

# ─── Ścieżki ────────────────────────────────────────────────────────────────
_AGENT_DIR  = Path(__file__).parent          # AI_devs4/agent/
_ROOT_DIR   = _AGENT_DIR.parent              # AI_devs4/
_TASKS_DIR  = _ROOT_DIR / "tasks"

# Sentinel w Select — "własny problem"
_CUSTOM_OPTION = "__custom__"


# ══════════════════════════════════════════════════════════════
# Modal: potwierdzenie usunięcia sesji
# ══════════════════════════════════════════════════════════════

class ConfirmDeleteModal(ModalScreen[bool]):
    """Prosi o potwierdzenie przed usunięciem folderu sesji."""

    DEFAULT_CSS = """
    ConfirmDeleteModal {
        align: center middle;
    }
    ConfirmDeleteModal > Vertical {
        width: 60;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }
    ConfirmDeleteModal Label {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }
    ConfirmDeleteModal Horizontal {
        width: 100%;
        align: center middle;
        margin-top: 1;
    }
    ConfirmDeleteModal Button {
        margin: 0 1;
    }
    """

    def __init__(self, task_name: str) -> None:
        super().__init__()
        self._task_name = task_name

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Usunąć sesję [bold]{self._task_name}[/bold]?")
            yield Label(f"Folder [italic]tasks/{self._task_name}/[/italic] zostanie trwale usunięty.")
            with Horizontal():
                yield Button("Tak, usuń", id="confirm-yes", variant="error")
                yield Button("Anuluj", id="confirm-no", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")


# ══════════════════════════════════════════════════════════════
# SessionRow — jeden wiersz sesji (własne compose())
# ══════════════════════════════════════════════════════════════

class SessionRow(Horizontal):
    """Wiersz sesji: nazwa + przycisk usunięcia. Używa compose() — bezpieczne w Textual."""

    DEFAULT_CSS = """
    SessionRow {
        height: 1;
        width: 100%;
        margin-bottom: 0;
    }
    SessionRow Label {
        width: 1fr;
        overflow-x: hidden;
    }
    SessionRow Button {
        width: 3;
        min-width: 3;
        height: 1;
        border: none;
        background: transparent;
        color: $error;
        padding: 0;
    }
    """

    def __init__(self, name: str) -> None:
        super().__init__(classes="session-row", id=f"row-{name}")
        self._session_name = name

    def compose(self) -> ComposeResult:
        yield Label(self._session_name, classes="session-name")
        yield Button("🗑", classes="del-btn", id=f"del-{self._session_name}")


# ══════════════════════════════════════════════════════════════
# SessionPanel — lista sesji z przyciskami usuwania
# ══════════════════════════════════════════════════════════════

class SessionPanel(ScrollableContainer):
    """Lewa kolumna — lista folderów tasks/ z opcją usuwania."""

    DEFAULT_CSS = """
    SessionPanel {
        width: 22;
        border-right: solid $primary-darken-2;
        padding: 0 1;
        background: $surface-darken-1;
    }
    SessionPanel Label.session-header {
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("📁 Sesje", classes="session-header")
        yield Static("", id="sessions-placeholder")

    # on_mount celowo pominięty — watch_agent_running(False) wywoła refresh_sessions()
    # przy inicjalizacji reaktywnej (Reactive._initialize_object), co wystarcza.

    def refresh_sessions(self) -> None:
        """Usuwa stare wiersze i kolejkuje montowanie nowych po ich usunięciu."""
        for row in self.query(".session-row"):
            row.remove()
        # call_after_refresh gwarantuje, że usunięcia zostaną przetworzone przed montem
        self.call_after_refresh(self._mount_sessions)

    def _mount_sessions(self) -> None:
        """Montuje wiersze sesji po wyczyszczeniu starych."""
        _TASKS_DIR.mkdir(parents=True, exist_ok=True)
        sessions = sorted(
            [d for d in _TASKS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        try:
            placeholder = self.query_one("#sessions-placeholder", Static)
        except NoMatches:
            return

        if not sessions:
            placeholder.update("[dim]brak sesji[/dim]")
        else:
            placeholder.update("")
            for sess in sessions:
                self.mount(SessionRow(sess.name))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("del-"):
            name = btn_id[4:]
            self.app.push_screen(ConfirmDeleteModal(name), self._handle_delete(name))
            event.stop()

    def _handle_delete(self, name: str):
        def callback(confirmed: bool) -> None:
            if confirmed:
                target = _TASKS_DIR / name
                if target.exists():
                    shutil.rmtree(target)
                self.refresh_sessions()
        return callback


# ══════════════════════════════════════════════════════════════
# TaskSetup — panel wyboru zadania (widoczny przed startem)
# ══════════════════════════════════════════════════════════════

class TaskSetup(Vertical):
    """Panel wyboru zadania — dropdown .md + textarea własnego problemu."""

    DEFAULT_CSS = """
    TaskSetup {
        padding: 1 2;
        height: auto;
    }
    TaskSetup Label.ts-label {
        margin-bottom: 0;
        color: $text-muted;
    }
    TaskSetup Select {
        width: 100%;
        margin-bottom: 1;
    }
    TaskSetup TextArea {
        height: 8;
        width: 100%;
        margin-bottom: 1;
    }
    TaskSetup Horizontal.ts-buttons {
        height: auto;
        width: 100%;
        margin-top: 1;
    }
    TaskSetup Button {
        margin-right: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Wybierz zadanie:", classes="ts-label")
        yield Select(
            options=self._get_task_options(),
            id="task-select",
            prompt="-- wybierz zadanie --",
        )
        yield Label("Własny problem (jeśli wybrano 'Własny...'):", classes="ts-label")
        yield TextArea(id="custom-task-input")
        with Horizontal(classes="ts-buttons"):
            yield Button("▶ Start", id="btn-start", variant="success")
            yield Button("▶ Start [Interaktywny]", id="btn-start-interactive", variant="primary")

    @staticmethod
    def _get_task_options() -> list[tuple[str, str]]:
        """Skanuje AI_devs4/*.md i zwraca listę opcji dla Select."""
        opts: list[tuple[str, str]] = []
        for p in sorted(_ROOT_DIR.glob("*.md")):
            opts.append((p.name, str(p)))
        opts.append(("✏️  Własny problem...", _CUSTOM_OPTION))
        return opts

    def refresh_options(self) -> None:
        """Odświeża opcje w Select (po powrocie do ekranu startowego)."""
        sel = self.query_one("#task-select", Select)
        sel.set_options(self._get_task_options())


# ══════════════════════════════════════════════════════════════
# InputBar — panel z pytaniem agenta (ukryty domyślnie)
# ══════════════════════════════════════════════════════════════

class InputBar(Vertical):
    """Pytanie agenta (wertykalny układ): Label z pytaniem, potem Input + Wyślij."""

    DEFAULT_CSS = """
    InputBar {
        height: auto;
        max-height: 7;
        border-top: solid $primary;
        background: $surface-darken-1;
        padding: 1 2;
    }
    InputBar Label.ib-question {
        width: 100%;
        height: auto;
        color: $warning;
        text-style: bold;
        margin-bottom: 1;
    }
    InputBar Horizontal.ib-row {
        height: 3;
        width: 100%;
    }
    InputBar Input {
        width: 1fr;
        margin-right: 1;
    }
    InputBar Button {
        width: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("", id="ib-question", classes="ib-question")
        with Horizontal(classes="ib-row"):
            yield Input(id="ib-input", placeholder="Twoja odpowiedź (Enter = akceptacja)...")
            yield Button("Wyślij ↵", id="ib-send", variant="primary")

    def on_mount(self) -> None:
        self.display = False

    def show_prompt(self, question: str, prompt_type: str) -> None:
        """Wyświetla pytanie i pokazuje pasek."""
        icon = {
            ioi.PT_PLAN:        "📋 PLAN — zaakceptuj lub wpisz uwagi:",
            ioi.PT_ASK_USER:    "❓ PYTANIE OD AGENTA:",
            ioi.PT_INTERACTIVE: "🎛 INTERAKTYWNY — zatwierdź krok lub wpisz sugestię:",
            ioi.PT_RESET:       "🔄 RESET KONTEKSTU — wpisz t/tak/y aby zaakceptować:",
        }.get(prompt_type, "❓")

        label = self.query_one("#ib-question", Label)
        label.update(f"{icon}  {question[:200]}")

        inp = self.query_one("#ib-input", Input)
        inp.value = ""
        self.display = True
        self.scroll_visible()
        inp.focus()

    def hide(self) -> None:
        self.display = False
        try:
            self.query_one("#ib-input", Input).value = ""
        except NoMatches:
            pass


# ══════════════════════════════════════════════════════════════
# AgentApp — główna aplikacja Textual
# ══════════════════════════════════════════════════════════════

class AgentApp(App):
    """Textual TUI dla agenta zadaniowego."""

    TITLE = "🤖 Agent UI"
    SUB_TITLE = "hub.ag3nts.org"
    ENABLE_COMMAND_PALETTE = False

    def bell(self) -> None:  # suppress terminal bell
        pass

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-area {
        layout: horizontal;
        height: 1fr;
    }

    SessionPanel {
        height: 100%;
    }

    #right-pane {
        width: 1fr;
        height: 100%;
        layout: vertical;
    }

    #task-setup {
        height: auto;
        border-bottom: solid $primary-darken-2;
    }

    #step-log {
        height: 1fr;
        border: none;
        background: $surface;
        padding: 0 1;
    }

    #header-controls {
        height: 3;
        align: right middle;
        padding: 0 2;
        background: $primary-darken-3;
    }

    #header-controls Label {
        margin-right: 1;
        color: $text;
    }

    #header-controls Switch {
        margin-right: 2;
    }

    #btn-graceful-stop {
        margin-right: 1;
    }

    #status-label {
        color: $success;
        margin-right: 2;
    }

    #status-label.running {
        color: $warning;
    }

    #status-label.stopped {
        color: $error;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Wyjście"),
        ("ctrl+q", "quit", "Wyjście"),
    ]

    # Reaktywny status agenta
    agent_running: reactive[bool] = reactive(False)

    def __init__(self) -> None:
        super().__init__()
        self._textual_io: ioi.TextualIO | None = None
        self._agent_thread: threading.Thread | None = None
        self._timer = None
        self._awaiting_input = False

    # ─── Compose ──────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()

        # Pasek kontrolny pod nagłówkiem
        with Horizontal(id="header-controls"):
            yield Label("Tryb interaktywny:")
            yield Switch(id="interactive-switch", value=False)
            yield Static("", id="status-label")
            yield Button("🛑 Stop", id="btn-graceful-stop", variant="warning")
            yield Button("⛔ Force Stop", id="btn-force-stop", variant="error")

        with Horizontal(id="main-area"):
            yield SessionPanel(id="session-panel")
            with Vertical(id="right-pane"):
                yield TaskSetup(id="task-setup")
                yield RichLog(id="step-log", highlight=True, markup=True, wrap=True)
                yield InputBar(id="input-bar")

        yield Footer()

    def on_mount(self) -> None:
        self._update_status("gotowy")
        # Ukryj przyciski stop na starcie (agent nie działa)
        self.query_one("#btn-graceful-stop", Button).display = False
        self.query_one("#btn-force-stop", Button).display = False

    # ─── Reaktywność agenta ───────────────────────────────────

    def watch_agent_running(self, running: bool) -> None:
        """Aktualizuje UI gdy agent startuje/kończy."""
        try:
            stop_btn  = self.query_one("#btn-graceful-stop", Button)
            force_btn = self.query_one("#btn-force-stop", Button)
            setup     = self.query_one("#task-setup", TaskSetup)
        except NoMatches:
            return

        if running:
            stop_btn.display = True
            force_btn.display = True
            setup.display = False
        else:
            stop_btn.display = False
            force_btn.display = False
            setup.display = True
            # Odśwież listę sesji i opcje zadań
            try:
                self.query_one("#session-panel", SessionPanel).refresh_sessions()
                self.query_one("#task-setup", TaskSetup).refresh_options()
            except NoMatches:
                pass

    # ─── Status label ─────────────────────────────────────────

    def _update_status(self, text: str, kind: str = "") -> None:
        try:
            lbl = self.query_one("#status-label", Static)
            lbl.update(text)
            lbl.remove_class("running", "stopped")
            if kind:
                lbl.add_class(kind)
        except NoMatches:
            pass

    # ─── Przyciski ────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""

        if bid == "btn-start":
            self._start_agent(interactive=False)
        elif bid == "btn-start-interactive":
            self._start_agent(interactive=True)
        elif bid == "ib-send":
            self._handle_user_answer()
        elif bid == "btn-graceful-stop":
            self._graceful_stop()
        elif bid == "btn-force-stop":
            self._force_stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "ib-input":
            self._handle_user_answer()

    # ─── Start agenta ─────────────────────────────────────────

    def _start_agent(self, interactive: bool) -> None:
        if self.agent_running:
            return

        # Ustal treść zadania
        task_text, task_name = self._get_task_text()
        if task_text is None:
            self._log_ui("⚠️  Wybierz zadanie lub wpisz własny problem.")
            return

        # Zainicjuj workspace
        try:
            sys.path.insert(0, str(_AGENT_DIR))
            task_md_path = self._prepare_task_file(task_text, task_name)
            ws.init(str(task_md_path))
        except Exception as exc:
            self._log_ui(f"❌  Błąd inicjalizacji workspace: {exc}")
            return

        # Wyczyść log
        log_widget = self.query_one("#step-log", RichLog)
        log_widget.clear()
        self._log_ui(f"▶  Startuje agent: {task_name}  [interactive={interactive}]")
        self._log_ui("─" * 55)

        # Ustaw TextualIO
        tio = ioi.TextualIO()
        self._textual_io = tio
        ioi.set_io(tio)

        # Ustaw reactive i status
        self.agent_running = True
        self._update_status("działa...", "running")

        # Uruchom timer drenowania kolejki
        self._timer = self.set_interval(0.05, self._drain_log_queue)

        # Uruchom agenta w wątku
        self._agent_thread = threading.Thread(
            target=agent_runner.run_in_thread,
            args=(task_text,),
            kwargs={"verbose": True, "interactive": interactive, "textual_io": tio},
            daemon=True,
        )
        self._agent_thread.start()

    def _get_task_text(self) -> tuple[str | None, str]:
        """Zwraca (treść zadania, nazwa sesji) lub (None, '') gdy nie wybrano."""
        try:
            sel = self.query_one("#task-select", Select)
            selected = sel.value
        except NoMatches:
            return None, ""

        if selected is Select.BLANK or selected is None:
            # Może być w textarea?
            pass
        elif selected == _CUSTOM_OPTION:
            pass  # przejdź do textarea
        else:
            # Ścieżka do pliku .md
            path = Path(str(selected))
            if path.exists():
                return path.read_text(encoding="utf-8"), path.stem
            return None, ""

        # Fallback: textarea
        try:
            ta = self.query_one("#custom-task-input", TextArea)
            text = ta.text.strip()
            if text:
                return text, "custom"
        except NoMatches:
            pass

        return None, ""

    def _prepare_task_file(self, task_text: str, task_name: str) -> Path:
        """Jeśli task_text pochodzi z textarea, zapisuje go jako .md i zwraca ścieżkę."""
        # Sprawdź czy już istnieje plik .md w _ROOT_DIR o tej nazwie
        existing = _ROOT_DIR / f"{task_name}.md"
        if existing.exists() and existing.read_text(encoding="utf-8") == task_text:
            return existing

        # Dla własnych problemów — stwórz/nadpisz plik w tasks/
        _TASKS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _ROOT_DIR / f"{task_name}.md"
        if task_name == "custom":
            # Zawsze świeży plik z timestampem by nie kolidować
            import datetime
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            task_name_ts = f"custom_{stamp}"
            tmp = _ROOT_DIR / f"{task_name_ts}.md"
        tmp.write_text(task_text, encoding="utf-8")
        return tmp

    # ─── Stop ─────────────────────────────────────────────────

    def _graceful_stop(self) -> None:
        if self._textual_io is not None:
            self._textual_io.request_stop()
            self._update_status("zatrzymywanie...", "running")
            self._log_ui("\n🛑  Graceful stop zażądany — agent zakończy bieżącą iterację.")

    def _force_stop(self) -> None:
        if self._textual_io is not None:
            self._textual_io.request_force_stop()
            self._update_status("wymuszono stop", "stopped")
            self._log_ui("\n⛔  Force stop — przerywam agenta natychmiast.")

    # ─── Drenaż kolejki ───────────────────────────────────────

    def _drain_log_queue(self) -> None:
        """Wywoływane co 50ms przez timer — czyta z log_queue i aktualizuje UI."""
        if self._textual_io is None:
            return

        q = self._textual_io.log_queue
        processed = 0
        while not q.empty() and processed < 200:
            try:
                line = q.get_nowait()
            except Exception:
                break
            processed += 1
            self._handle_queue_item(line)

    def _handle_queue_item(self, item: str) -> None:
        """Obsługuje pojedynczy wpis z kolejki."""
        if item.startswith(ioi.INPUT_SENTINEL + ":"):
            # Format: __INPUT_REQUIRED__:<typ>:<pytanie>
            rest = item[len(ioi.INPUT_SENTINEL) + 1:]
            typ, _, question = rest.partition(":")
            self._show_input_bar(question, typ)
            return

        if item == ioi.DONE_SENTINEL:
            self._on_agent_done(stopped=False)
            return

        if item == ioi.STOPPED_SENTINEL:
            self._on_agent_done(stopped=True)
            return

        # Zwykła linia logu
        self._log_ui(item)

    def _log_ui(self, text: str) -> None:
        """Wpisuje tekst do RichLog."""
        try:
            log_widget = self.query_one("#step-log", RichLog)
            log_widget.write(text)
        except NoMatches:
            pass

    # ─── Input bar ────────────────────────────────────────────

    def _show_input_bar(self, question: str, prompt_type: str) -> None:
        self._awaiting_input = True
        try:
            bar = self.query_one("#input-bar", InputBar)
            bar.show_prompt(question, prompt_type)
            # Upewnij się, że RichLog ustąpi miejsca InputBar
            self.query_one("#step-log", RichLog).scroll_end(animate=False)
        except NoMatches:
            pass

    def _handle_user_answer(self) -> None:
        if not self._awaiting_input or self._textual_io is None:
            return
        try:
            inp = self.query_one("#ib-input", Input)
            answer = inp.value.strip()
            bar = self.query_one("#input-bar", InputBar)
            bar.hide()
        except NoMatches:
            return

        self._awaiting_input = False
        self._log_ui(f"[bold cyan]  Twoja odpowiedź:[/bold cyan] {answer or '(Enter)'}")
        self._textual_io.set_answer(answer)

    # ─── Zakończenie agenta ───────────────────────────────────

    def _on_agent_done(self, stopped: bool) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

        # Opróżnij resztę kolejki
        if self._textual_io:
            q = self._textual_io.log_queue
            while not q.empty():
                try:
                    line = q.get_nowait()
                    if not line.startswith(ioi.INPUT_SENTINEL) \
                       and line not in (ioi.DONE_SENTINEL, ioi.STOPPED_SENTINEL):
                        self._log_ui(line)
                except Exception:
                    break

        # Ukryj InputBar jeśli widoczny
        try:
            self.query_one("#input-bar", InputBar).hide()
        except NoMatches:
            pass
        self._awaiting_input = False

        if stopped:
            self._update_status("zatrzymany", "stopped")
            self._log_ui("\n─" * 55)
            self._log_ui("🛑  Agent zatrzymany.")
        else:
            self._update_status("gotowy", "")
            self._log_ui("\n─" * 55)
            self._log_ui("✅  Agent zakończył pracę.")

        self.agent_running = False
        ioi.set_io(ioi.TerminalIO())
        self._textual_io = None


# ─── Punkt wejścia ────────────────────────────────────────────

def run_ui() -> None:
    """Uruchamia Textual TUI. Wywoływane z __main__.py przez --ui."""
    app = AgentApp()
    app.run()


if __name__ == "__main__":
    run_ui()
