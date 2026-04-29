"""
Punkt wejścia agenta.
Użycie:
  python agent <plik_zadania.md>       — tryb terminalowy
  python agent -i <plik_zadania.md>    — tryb interaktywny
  python agent --ui                    — Textual TUI
"""
import argparse
import sys
import workspace as ws
import runner


def main():
    parser = argparse.ArgumentParser(
        description="Agent zadaniowy hub.ag3nts.org",
        usage="python agent [--ui] | python agent [-i] <plik_zadania.md>",
    )
    parser.add_argument(
        "task_file",
        nargs="?",
        help="Plik .md z treścią zadania (wymagany bez --ui)",
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Tryb interaktywny: agent prezentuje planowany krok przed wykonaniem",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Uruchom Textual TUI zamiast trybu terminalowego",
    )
    args = parser.parse_args()

    # ─── Tryb Web UI ──────────────────────────────────────────
    if args.ui:
        try:
            from web_ui import run_web_ui
        except ImportError as exc:
            print(f"Błąd importu Web UI: {exc}", file=sys.stderr)
            print("Zainstaluj: pip install fastapi 'uvicorn[standard]'", file=sys.stderr)
            sys.exit(1)
        run_web_ui()
        return

    # ─── Tryb terminalowy ─────────────────────────────────────
    if not args.task_file:
        parser.error("Podaj plik zadania lub użyj --ui")

    md_file   = args.task_file
    task_text, workspace = ws.init(md_file)

    print(f"\n{'═' * 55}")
    print(f"  AGENT ZADANIOWY — hub.ag3nts.org")
    print(f"{'═' * 55}")
    print(f"  📄 Zadanie  : {md_file}")
    print(f"  📁 Workspace: {workspace}/")
    print(f"     ├── task.md      (treść zadania)")
    print(f"     ├── history.md   (log operacji)")
    print(f"     ├── cache/       (pobrane zasoby)")
    print(f"     └── output/      (wyniki agenta)")
    print(f"{'═' * 55}")
    print(f"  🤖 Subagenci: vision, web, text")
    if args.interactive:
        print(f"  🎛  Tryb      : INTERAKTYWNY (-i)")
    print(f"{'═' * 55}\n")

    runner.run(task_text, interactive=args.interactive)


if __name__ == "__main__":
    main()

