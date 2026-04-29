"""
web_ui.py — FastAPI Web UI dla agenta zadaniowego.

Uruchomienie:
    python agent --ui          → http://127.0.0.1:8765

Architektura:
  - FastAPI + uvicorn jako serwer HTTP/WebSocket
  - Jeden endpoint WebSocket /ws — full-duplex komunikacja z przeglądarką
  - Agent działa w osobnym wątku, komunikuje się przez TextualIO (kolejki)
  - Async _drain_loop() czyta z log_queue i wysyła do WebSocket co ~30ms
  - Obsługuje reconnect: po powrocie przeglądarki wznawia draining jeśli agent nadal działa

Protocol (JSON):
  Server → Client:
    {"type": "sessions", "sessions": [...]}
    {"type": "tasks", "tasks": [{"name": "...", "path": "..."}]}
    {"type": "running", "is_running": bool}
    {"type": "agent_started", "task_name": "...", "interactive": bool}
    {"type": "agent_done"} / {"type": "agent_stopped"}
    {"type": "log", "text": "..."}
    {"type": "input_request", "prompt_type": "plan|ask_user|interactive|reset", "question": "..."}
    {"type": "error", "message": "..."}

  Client → Server:
    {"type": "start", "task_path": "...", "interactive": bool}
    {"type": "start_custom", "task_text": "...", "interactive": bool}
    {"type": "answer", "text": "..."}
    {"type": "graceful_stop"} / {"type": "force_stop"}
    {"type": "delete_session", "name": "..."}
    {"type": "get_sessions"} / {"type": "get_tasks"}
"""
from __future__ import annotations

import asyncio
import datetime
import json
import queue
import shutil
import sys
import threading
from pathlib import Path

try:
    import uvicorn
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse
except ImportError as exc:
    raise ImportError(
        f"Brakujące zależności Web UI: {exc}\n"
        "Zainstaluj: pip install fastapi 'uvicorn[standard]'"
    ) from exc

import workspace as ws
import runner as agent_runner
import io_interface as ioi
from io_interface import TextualIO, INPUT_SENTINEL, DONE_SENTINEL, STOPPED_SENTINEL

# ─── Ścieżki ─────────────────────────────────────────────────────
_AGENT_DIR  = Path(__file__).parent   # AI_devs4/agent/
_ROOT_DIR   = _AGENT_DIR.parent       # AI_devs4/
_TASKS_DIR  = _ROOT_DIR / "tasks"
_HTML_FILE  = _AGENT_DIR / "static" / "index.html"

app = FastAPI(title="Agent UI", docs_url=None, redoc_url=None)


# ══════════════════════════════════════════════════════════════════
# Stan agenta (singleton)
# ══════════════════════════════════════════════════════════════════

class _AgentState:
    """Współdzielony stan agenta — jeden wątek na raz."""

    def __init__(self) -> None:
        self.textual_io: TextualIO | None = None
        self.agent_thread: threading.Thread | None = None
        self._drain_task: asyncio.Task | None = None

    def is_running(self) -> bool:
        return bool(self.agent_thread and self.agent_thread.is_alive())

    def cancel_drain(self) -> None:
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
        self._drain_task = None

    def clear(self) -> None:
        self.cancel_drain()
        self.textual_io = None
        self.agent_thread = None


_agent = _AgentState()


# ══════════════════════════════════════════════════════════════════
# Pomocniki protokołu
# ══════════════════════════════════════════════════════════════════

def _sessions_payload() -> dict:
    _TASKS_DIR.mkdir(parents=True, exist_ok=True)
    sessions = sorted(
        [d.name for d in _TASKS_DIR.iterdir()
         if d.is_dir() and not d.name.startswith(".")],
        key=lambda n: (_TASKS_DIR / n).stat().st_mtime,
        reverse=True,
    )
    return {"type": "sessions", "sessions": sessions}


def _tasks_payload() -> dict:
    tasks = [
        {"name": p.name, "path": str(p)}
        for p in sorted(_ROOT_DIR.glob("*.md"))
    ]
    return {"type": "tasks", "tasks": tasks}


def _poll_queue(tio: TextualIO) -> str | None:
    try:
        return tio.log_queue.get_nowait()
    except queue.Empty:
        return None


# ══════════════════════════════════════════════════════════════════
# Drain loop — async task bridging wątek agenta ↔ WebSocket
# ══════════════════════════════════════════════════════════════════

async def _drain_loop(ws_conn: WebSocket, tio: TextualIO) -> None:
    """
    Opróżnia log_queue agenta i wysyła wiadomości do WebSocket.
    Działa jako asyncio.Task — nie blokuje event loop.
    """
    loop = asyncio.get_running_loop()
    while True:
        try:
            item = await loop.run_in_executor(None, _poll_queue, tio)
            if item is None:
                await asyncio.sleep(0.03)
                continue

            if item.startswith(INPUT_SENTINEL + ":"):
                rest = item[len(INPUT_SENTINEL) + 1:]
                prompt_type, _, question = rest.partition(":")
                await ws_conn.send_json({
                    "type":        "input_request",
                    "prompt_type": prompt_type,
                    "question":    question,
                })

            elif item == DONE_SENTINEL:
                await ws_conn.send_json({"type": "agent_done"})
                await ws_conn.send_json(_sessions_payload())
                _agent.clear()
                break

            elif item == STOPPED_SENTINEL:
                await ws_conn.send_json({"type": "agent_stopped"})
                await ws_conn.send_json(_sessions_payload())
                _agent.clear()
                break

            else:
                await ws_conn.send_json({"type": "log", "text": item})

        except asyncio.CancelledError:
            break
        except Exception:
            break


# ══════════════════════════════════════════════════════════════════
# WebSocket endpoint
# ══════════════════════════════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    # Wyślij stan początkowy
    await websocket.send_json(_sessions_payload())
    await websocket.send_json(_tasks_payload())
    await websocket.send_json({"type": "running", "is_running": _agent.is_running()})

    # Jeśli agent nadal działa (np. po reconnect) — wznów draining
    _agent.cancel_drain()
    if _agent.is_running() and _agent.textual_io:
        _agent._drain_task = asyncio.create_task(
            _drain_loop(websocket, _agent.textual_io)
        )

    try:
        async for raw in websocket.iter_text():
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            # ── Start agenta ──────────────────────────────────────
            if msg_type in ("start", "start_custom"):
                if _agent.is_running():
                    await websocket.send_json({
                        "type":    "error",
                        "message": "Agent już działa — zatrzymaj go przed uruchomieniem nowego zadania.",
                    })
                    continue

                interactive = bool(msg.get("interactive", False))

                if msg_type == "start":
                    task_path = Path(msg["task_path"])
                    if not task_path.exists():
                        await websocket.send_json({
                            "type":    "error",
                            "message": f"Plik nie istnieje: {task_path}",
                        })
                        continue
                    task_text = task_path.read_text(encoding="utf-8")
                    task_name = task_path.stem
                    task_md   = task_path
                else:
                    task_text = msg.get("task_text", "").strip()
                    if not task_text:
                        await websocket.send_json({
                            "type":    "error",
                            "message": "Treść zadania jest pusta.",
                        })
                        continue
                    stamp     = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    task_name = f"custom_{stamp}"
                    task_md   = _ROOT_DIR / f"{task_name}.md"
                    task_md.write_text(task_text, encoding="utf-8")

                # Init workspace
                try:
                    ws.init(str(task_md))
                except Exception as exc:
                    await websocket.send_json({
                        "type":    "error",
                        "message": f"Błąd inicjalizacji workspace: {exc}",
                    })
                    continue

                # Setup TextualIO
                tio = TextualIO()
                ioi.set_io(tio)
                _agent.textual_io = tio

                # Drain task
                _agent.cancel_drain()
                _agent._drain_task = asyncio.create_task(
                    _drain_loop(websocket, tio)
                )

                # Wątek agenta
                t = threading.Thread(
                    target=agent_runner.run_in_thread,
                    args=(task_text,),
                    kwargs={
                        "verbose":     True,
                        "interactive": interactive,
                        "textual_io":  tio,
                    },
                    daemon=True,
                )
                t.start()
                _agent.agent_thread = t

                await websocket.send_json({
                    "type":        "agent_started",
                    "task_name":   task_name,
                    "interactive": interactive,
                })

            # ── Odpowiedź użytkownika ─────────────────────────────
            elif msg_type == "answer":
                if _agent.textual_io:
                    _agent.textual_io.set_answer(msg.get("text", ""))

            # ── Graceful stop ─────────────────────────────────────
            elif msg_type == "graceful_stop":
                if _agent.textual_io:
                    _agent.textual_io.request_stop()
                    await websocket.send_json({
                        "type": "log",
                        "text": "🛑  Graceful stop zażądany — agent zakończy bieżącą iterację.",
                    })

            # ── Force stop ────────────────────────────────────────
            elif msg_type == "force_stop":
                if _agent.textual_io:
                    _agent.textual_io.request_force_stop()
                    await websocket.send_json({
                        "type": "log",
                        "text": "⛔  Force stop — przerywam agenta natychmiast.",
                    })

            # ── Zarządzanie sesjami ───────────────────────────────
            elif msg_type == "delete_session":
                name = msg.get("name", "")
                if name:
                    target = _TASKS_DIR / name
                    if target.exists() and target.is_dir():
                        shutil.rmtree(target)
                await websocket.send_json(_sessions_payload())

            elif msg_type == "get_sessions":
                await websocket.send_json(_sessions_payload())

            elif msg_type == "get_tasks":
                await websocket.send_json(_tasks_payload())

    except WebSocketDisconnect:
        pass
    finally:
        _agent.cancel_drain()


# ══════════════════════════════════════════════════════════════════
# HTML endpoint
# ══════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(content=_HTML_FILE.read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════════
# Punkt wejścia
# ══════════════════════════════════════════════════════════════════

def run_web_ui(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Uruchamia Web UI. Wywoływane z __main__.py przez --ui."""
    import webbrowser
    import time

    url = f"http://{host}:{port}"
    print(f"\n{'═' * 55}")
    print(f"  🌐 Agent Web UI")
    print(f"{'═' * 55}")
    print(f"  Adres  : {url}")
    print(f"  Ctrl+C : zatrzymaj serwer")
    print(f"{'═' * 55}\n")

    def _open_browser() -> None:
        time.sleep(1.2)
        webbrowser.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
