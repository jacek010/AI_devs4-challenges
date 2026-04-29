"""
io_interface.py — abstrakcja nad input() i print() dla agenta.

Dwa tryby:
  TerminalIO   — zachowuje istniejące zachowanie CLI (zwykłe input())
  TextualIO    — wersja dla TUI Textual:
                  • log_queue    — kolejka linii tekstu do wyświetlenia w UI
                  • input_event  — Event blokujący wątek agenta do czasu odpowiedzi
                  • stop_event   — flaga graceful stop (agent kończy bieżący krok)
                  • force_stop_event — flaga natychmiastowego przerwania

Użycie:
  import io_interface
  io_interface.set_io(TextualIO())       # przed startem wątku agenta
  answer = io_interface.prompt_user("Pytanie?", "plan")
  io_interface.enqueue_log("Linia logu")
"""
from __future__ import annotations

import io
import queue
import re
import threading
from abc import ABC, abstractmethod

# ─── Sentinel values w log_queue ──────────────────────────────
# Wysyłane do kolejki zamiast zwykłego tekstu:
#   "__INPUT_REQUIRED__:<typ>:<pytanie>"  — UI musi pokazać input
#   "__AGENT_DONE__"                      — wątek agenta się zakończył
#   "__AGENT_STOPPED__"                   — wątek zatrzymany przez stop
INPUT_SENTINEL   = "__INPUT_REQUIRED__"
DONE_SENTINEL    = "__AGENT_DONE__"
STOPPED_SENTINEL = "__AGENT_STOPPED__"

# Typy promptów (przekazywane jako prompt_type):
PT_PLAN         = "plan"
PT_ASK_USER     = "ask_user"
PT_INTERACTIVE  = "interactive"
PT_RESET        = "reset"

# Kody ANSI — regex do stripowania
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mABCDEFGHJKSTfhilmnprsu]')


# ══════════════════════════════════════════════════════════════
# ABC
# ══════════════════════════════════════════════════════════════

class IOInterface(ABC):
    """Interfejs I/O — implementowany przez TerminalIO lub TextualIO."""

    @abstractmethod
    def prompt_user(self, question: str, prompt_type: str = PT_ASK_USER) -> str:
        """Pyta użytkownika i zwraca odpowiedź (blokuje do czasu udzielenia)."""

    @abstractmethod
    def enqueue_log(self, text: str) -> None:
        """Przekazuje linię logu do odpowiedniego celu (terminal / kolejka UI)."""

    def is_stop_requested(self) -> bool:
        """Graceful stop — agent może sprawdzić na początku każdej iteracji."""
        return False

    def is_force_stop_requested(self) -> bool:
        """Force stop — natychmiastowe przerwanie."""
        return False


# ══════════════════════════════════════════════════════════════
# TerminalIO — identyczne zachowanie jak dotychczasowe input()
# ══════════════════════════════════════════════════════════════

class TerminalIO(IOInterface):
    """CLI mode — print/input zachowują się tak samo jak przed refaktorem."""

    def prompt_user(self, question: str, prompt_type: str = PT_ASK_USER) -> str:  # noqa: ARG002
        return input().strip()

    def enqueue_log(self, text: str) -> None:
        # W trybie terminalowym log już trafił przez print() — nie robimy nic
        pass


# ══════════════════════════════════════════════════════════════
# TextualIO — wersja dla TUI
# ══════════════════════════════════════════════════════════════

class TextualIO(IOInterface):
    """
    Wersja dla Textual TUI:
      - enqueue_log()   — wrzuca tekst do log_queue (odbierany przez Textual timer)
      - prompt_user()   — wrzuca sentinel + blokuje na input_event
      - Dwa eventy stop: stop_event (graceful) i force_stop_event (natychmiastowy)
    """

    def __init__(self) -> None:
        self.log_queue: queue.SimpleQueue[str] = queue.SimpleQueue()
        self.input_event   = threading.Event()
        self.input_answer  = ""
        self._input_lock   = threading.Lock()

        self.stop_event       = threading.Event()
        self.force_stop_event = threading.Event()

    # ─── Logging ──────────────────────────────────────────────

    def enqueue_log(self, text: str) -> None:
        """Wrzuca tekst (po stripowaniu ANSI) do kolejki."""
        self.log_queue.put(text)

    # ─── Input ────────────────────────────────────────────────

    def prompt_user(self, question: str, prompt_type: str = PT_ASK_USER) -> str:
        """
        Wysyła sentinel do kolejki, blokuje wątek agenta i czeka na odpowiedź z UI.
        Rzuca AgentStoppedException gdy force_stop_event ustawiony przed lub w trakcie oczekiwania.
        """
        sentinel = f"{INPUT_SENTINEL}:{prompt_type}:{question}"
        self.log_queue.put(sentinel)

        # Zresetuj event przed blokowaniem
        with self._input_lock:
            self.input_event.clear()
            self.input_answer = ""

        # Czekaj na odpowiedź lub force stop (sprawdzaj co 100ms)
        while True:
            answered = self.input_event.wait(timeout=0.1)
            if answered:
                with self._input_lock:
                    return self.input_answer
            if self.force_stop_event.is_set():
                raise AgentStoppedException("Force stop during user input")

    def set_answer(self, answer: str) -> None:
        """Wywoływane z wątku UI gdy użytkownik poda odpowiedź."""
        with self._input_lock:
            self.input_answer = answer
        self.input_event.set()

    # ─── Stop flags ───────────────────────────────────────────

    def is_stop_requested(self) -> bool:
        return self.stop_event.is_set()

    def is_force_stop_requested(self) -> bool:
        return self.force_stop_event.is_set()

    def request_stop(self) -> None:
        """Graceful stop — agent zakończy po bieżącej iteracji."""
        self.stop_event.set()
        # Jeśli agent czeka na input — odblokuj z pustą odpowiedzią
        with self._input_lock:
            if not self.input_event.is_set():
                self.input_answer = ""
                self.input_event.set()

    def request_force_stop(self) -> None:
        """Force stop — przerywa natychmiastowo (rzuca wyjątek w prompt_user)."""
        self.force_stop_event.set()
        self.stop_event.set()
        # Odblokuj ewentualne oczekiwanie na input
        with self._input_lock:
            if not self.input_event.is_set():
                self.input_answer = ""
                self.input_event.set()

    def signal_done(self) -> None:
        """Wysyła sentinel zakończenia do kolejki UI."""
        self.log_queue.put(DONE_SENTINEL)

    def signal_stopped(self) -> None:
        """Wysyła sentinel zatrzymania do kolejki UI."""
        self.log_queue.put(STOPPED_SENTINEL)


# ══════════════════════════════════════════════════════════════
# AgentStoppedException
# ══════════════════════════════════════════════════════════════

class AgentStoppedException(Exception):
    """Rzucany gdy force_stop_event jest ustawiony podczas działania agenta."""


# ══════════════════════════════════════════════════════════════
# UIStream — przekierowanie sys.stdout do kolejki TUI
# ══════════════════════════════════════════════════════════════

class UIStream(io.TextIOBase):
    """
    Podmiana sys.stdout — przechwytuje wszystkie print() agenta.
    Strippuje kody ANSI i wrzuca tekst do io_interface.enqueue_log().
    Textual renderuje się własnym mechanizmem (nie przez stdout) — bezpieczne.
    """

    def __init__(self, textual_io: TextualIO) -> None:
        super().__init__()
        self._tio = textual_io
        self._buf = ""

    def write(self, text: str) -> int:
        if not isinstance(text, str):
            text = str(text)
        # Buforuj do \n, żeby do kolejki trafiały pełne linie
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            stripped = _ANSI_RE.sub("", line)
            if stripped or line:  # wyślij nawet pustą linię (wizualny odstęp)
                self._tio.enqueue_log(stripped)
        return len(text)

    def flush(self) -> None:
        # Wyślij to co zostało w buforze (bez \n), np. prompty z end=""
        if self._buf:
            stripped = _ANSI_RE.sub("", self._buf)
            self._tio.enqueue_log(stripped)
            self._buf = ""

    @property
    def encoding(self) -> str:
        return "utf-8"

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True


# ══════════════════════════════════════════════════════════════
# Globalny singleton
# ══════════════════════════════════════════════════════════════

_current: IOInterface = TerminalIO()


def set_io(io_impl: IOInterface) -> None:
    """Ustawia globalną implementację I/O (wywołaj przed startem wątku agenta)."""
    global _current
    _current = io_impl


def get_io() -> IOInterface:
    """Zwraca bieżącą implementację I/O."""
    return _current


def prompt_user(question: str, prompt_type: str = PT_ASK_USER) -> str:
    """Globalny proxy — pyta użytkownika przez bieżącą implementację I/O."""
    return _current.prompt_user(question, prompt_type)


def enqueue_log(text: str) -> None:
    """Globalny proxy — wysyła tekst do bieżącej implementacji I/O."""
    _current.enqueue_log(text)


def is_stop_requested() -> bool:
    """Sprawdza flagę graceful stop."""
    return _current.is_stop_requested()


def is_force_stop_requested() -> bool:
    """Sprawdza flagę force stop."""
    return _current.is_force_stop_requested()
