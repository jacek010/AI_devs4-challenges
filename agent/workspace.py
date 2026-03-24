from __future__ import annotations
from pathlib import Path
from datetime import datetime
import hashlib

# Globalny singleton workspace — inicjowany raz przy starcie
_root: Path | None = None


# ═══════════════════════════════════════════════════════════════
# Inicjalizacja
# ═══════════════════════════════════════════════════════════════

def init(md_file: str) -> tuple[str, Path]:
    """
    Tworzy folder roboczy o nazwie pliku .md (bez rozszerzenia).
    Zwraca (treść zadania, ścieżka workspace).

    Struktura:
        s01e03/
        ├── task.md        ← kopia treści zadania
        ├── history.md     ← append-only log operacji
        ├── cache/         ← pobrane pliki z internetu
        └── output/        ← wyniki agenta, deklaracje, odpowiedzi
    """
    global _root

    md_path = Path(md_file)
    if not md_path.exists():
        raise FileNotFoundError(f"Plik zadania nie istnieje: {md_file}")

    task_text = md_path.read_text(encoding="utf-8")

    _root = Path("tasks") / md_path.stem
    _root.mkdir(parents=True, exist_ok=True)
    (_root / "cache").mkdir(exist_ok=True)
    (_root / "output").mkdir(exist_ok=True)

    task_copy = _root / "task.md"
    if not task_copy.exists():
        task_copy.write_text(task_text, encoding="utf-8")

    log("INIT", f"Workspace: {_root}/  |  Zadanie: {md_file}")
    return task_text, _root


def root() -> Path:
    if _root is None:
        raise RuntimeError("Workspace nie został zainicjowany. Wywołaj workspace.init() najpierw.")
    return _root


# ═══════════════════════════════════════════════════════════════
# Historia operacji
# ═══════════════════════════════════════════════════════════════

def log(event: str, detail: str, preview: str = "") -> None:
    """Dopisuje wpis do history.md (append-only, nigdy nie nadpisuje)."""
    if _root is None:
        return
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"## [{ts}] {event}\n{detail}\n"
    if preview:
        clipped = preview[:400] + ("…" if len(preview) > 400 else "")
        body += f"```\n{clipped}\n```\n"
    body += "\n"
    with (_root / "history.md").open("a", encoding="utf-8") as f:
        f.write(body)


# ═══════════════════════════════════════════════════════════════
# Cache — pobrane pliki z internetu
# ═══════════════════════════════════════════════════════════════

def cache_key(url: str, suffix: str = "") -> str:
    """Generuje unikalną, bezpieczną nazwę pliku dla danego URL."""
    h    = hashlib.md5(url.encode()).hexdigest()[:6]
    name = url.split("/")[-1].split("?")[0]
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    safe = safe[:60] or "resource"
    return f"{h}_{safe}{suffix}"


def cache_read(key: str) -> str | None:
    """Czyta plik z cache/. Zwraca None jeśli nie istnieje."""
    path = root() / "cache" / key
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return path.read_bytes().decode("latin-1")
    return None


def cache_write(key: str, content: str | bytes) -> None:
    """Zapisuje plik do cache/."""
    path = root() / "cache" / key
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def cache_read_bytes(key: str) -> bytes | None:
    """Czyta plik binarny z cache/."""
    path = root() / "cache" / key
    return path.read_bytes() if path.exists() else None


# ═══════════════════════════════════════════════════════════════
# Output — wyniki agenta
# ═══════════════════════════════════════════════════════════════

def output_write(filename: str, content: str) -> Path:
    """Zapisuje plik do output/."""
    path = root() / "output" / filename
    path.write_text(content, encoding="utf-8")
    return path


def output_read(filename: str) -> str | None:
    """Czyta plik z output/."""
    path = root() / "output" / filename
    return path.read_text(encoding="utf-8") if path.exists() else None


def find_file(name: str) -> str | None:
    """Szuka pliku w output/ i cache/ — najpierw dokładne dopasowanie, potem częściowe."""
    for subdir in ("output", "cache"):
        exact = root() / subdir / name
        if exact.exists():
            return exact.read_text(encoding="utf-8")
    for subdir in ("output", "cache"):
        matches = sorted((root() / subdir).glob(f"*{name}*"))
        if matches:
            return matches[0].read_text(encoding="utf-8")
    return None


def ls() -> str:
    """Zwraca sformatowaną listę plików w workspace."""
    lines = []
    for subdir in ("cache", "output"):
        files = sorted((root() / subdir).iterdir())
        files = [f for f in files if f.is_file()]
        if files:
            lines.append(f"📁 {subdir}/ ({len(files)} plików):")
            for f in files:
                lines.append(f"   {f.name}  [{f.stat().st_size:,} B]")
    return "\n".join(lines) if lines else "Workspace pusty."
