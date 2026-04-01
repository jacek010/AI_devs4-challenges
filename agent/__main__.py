"""
Punkt wejścia agenta.
Użycie: python agent s01e03.md
"""
import sys
import workspace as ws
import runner


def main():
    if len(sys.argv) < 2:
        print("Użycie:  python agent <plik_zadania.md>")
        print("Przykład: python agent s01e03.md")
        sys.exit(1)

    md_file   = sys.argv[1]
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
    print(f"  🤖 Subagenci: vision")
    print(f"{'═' * 55}\n")

    runner.run(task_text)


if __name__ == "__main__":
    main()
