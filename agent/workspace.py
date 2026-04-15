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
    # Strip redundant output/ prefix to avoid output/output/ duplication
    if filename.startswith("output/"):
        filename = filename[len("output/"):]
    path = root() / "output" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def output_read(filename: str) -> str | None:
    """Czyta plik z output/."""
    path = root() / "output" / filename
    return path.read_text(encoding="utf-8") if path.exists() else None


def find_file(name: str) -> str | None:
    """Szuka pliku w rootu workspace, output/ i cache/ — najpierw dokładne dopasowanie, potem częściowe (rekurencyjne)."""
    # Szukaj w korzeniu workspace — m.in. task.md, history.md
    exact_root = root() / name
    if exact_root.exists() and exact_root.is_file():
        return exact_root.read_text(encoding="utf-8")
    for subdir in ("output", "cache"):
        exact = root() / subdir / name
        if exact.exists() and exact.is_file():
            return exact.read_text(encoding="utf-8")
    # Częściowe dopasowanie — korzeń, output, cache
    root_matches = sorted(p for p in root().iterdir() if p.is_file() and name.lower() in p.name.lower())
    if root_matches:
        return root_matches[0].read_text(encoding="utf-8")
    for subdir in ("output", "cache"):
        matches = sorted((root() / subdir).rglob(f"*{name}*"))
        matches = [m for m in matches if m.is_file()]
        if matches:
            return matches[0].read_text(encoding="utf-8")
    return None


def ls() -> str:
    """Zwraca sformatowaną listę plików w workspace (rekurencyjnie).

    Pliki bezpośrednio w cache/ lub output/ — zawsze pełna lista.
    Pliki w podfolderach: jeśli > LS_DIR_THRESHOLD, wyświetl skrót
    z generalizacją (count, typy, zakres rozmiarów, kilka przykładów).
    """
    import config as _cfg
    from collections import defaultdict

    lines = []

    # Pliki bezpośrednio w rootu workspace (task.md, history.md, memory_journal.md, ...)
    root_files = sorted(f for f in root().iterdir() if f.is_file())
    if root_files:
        lines.append("📄 (korzeń workspace):")
        for f in root_files:
            lines.append(f"   {f.name}  [{f.stat().st_size:,} B]")

    for subdir in ("cache", "output"):
        base = root() / subdir
        all_files = sorted(f for f in base.rglob("*") if f.is_file())
        if not all_files:
            continue

        lines.append(f"📁 {subdir}/ ({len(all_files)} plików):")

        # Pogrupuj: klucz = pierwsza część ścieżki względnej (podfolder lub '.')
        groups: dict[str, list[Path]] = defaultdict(list)
        for f in all_files:
            rel = f.relative_to(base)
            key = rel.parts[0] if len(rel.parts) > 1 else "."
            groups[key].append(f)

        for key in sorted(groups):
            group_files = groups[key]
            if key == ".":
                # Pliki bezpośrednio w subdir — zawsze pełna lista
                for f in group_files:
                    rel = f.relative_to(base)
                    lines.append(f"   {rel}  [{f.stat().st_size:,} B]")
            elif len(group_files) <= _cfg.LS_DIR_THRESHOLD:
                # Mały podfolder — pełna lista
                for f in group_files:
                    rel = f.relative_to(base)
                    lines.append(f"   {rel}  [{f.stat().st_size:,} B]")
            else:
                # Duży podfolder — skrót z generalizacją
                sizes = [f.stat().st_size for f in group_files]
                exts: dict[str, int] = defaultdict(int)
                for f in group_files:
                    exts[f.suffix.lower() or "(brak)"] += 1
                ext_summary = ", ".join(
                    f"{cnt}x {ext}" for ext, cnt in sorted(exts.items(), key=lambda x: -x[1])
                )
                lines.append(
                    f"   📂 {key}/ — {len(group_files)} plików ({ext_summary})"
                    f" | rozmiar: {min(sizes):,}–{max(sizes):,} B"
                )
                # 3 pierwsze + 3 ostatnie przykłady
                examples_head = [f.relative_to(base) for f in group_files[:3]]
                examples_tail = [f.relative_to(base) for f in group_files[-3:]]
                head_str = ", ".join(str(p) for p in examples_head)
                tail_str = ", ".join(str(p) for p in examples_tail)
                lines.append(f"        Przykłady: {head_str}")
                lines.append(f"                   … {tail_str}")

    return "\n".join(lines) if lines else "Workspace pusty."


# ═══════════════════════════════════════════════════════════════
# Observational Memory — pamięć cross-session
# ═══════════════════════════════════════════════════════════════

def journal_path() -> Path:
    """Ścieżka do pliku dziennika pamięci cross-session."""
    return root() / "memory_journal.md"


def journal_read() -> str:
    """Czyta aktualny dziennik pamięci. Zwraca pusty string jeśli nie istnieje."""
    p = journal_path()
    return p.read_text(encoding="utf-8") if p.exists() else ""


def journal_append(entry: str, task_name: str = "") -> None:
    """Dopisuje nowy wpis-obserwację do dziennika (Observer).
    task_name: identyfikator zadania — pojawia się w metadanych wpisu (#26).
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    task_tag = f" | task: {task_name}" if task_name else ""
    with journal_path().open("a", encoding="utf-8") as f:
        f.write(f"\n---\n[{ts}{task_tag}]\n{entry.strip()}\n")
    log("JOURNAL_APPEND", f"Nowy wpis do memory_journal.md ({len(entry)} znaków)")


def journal_write(content: str) -> None:
    """Nadpisuje dziennik skompresowaną wersją (Reflector)."""
    journal_path().write_text(content, encoding="utf-8")
    log("JOURNAL_WRITE", f"Przepisano memory_journal.md ({len(content)} znaków)")
