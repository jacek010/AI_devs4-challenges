"""
Punkt wejścia agenta.
Użycie: python agent [-i] s01e03.md
"""
import argparse
import workspace as ws
import runner


def main():
    parser = argparse.ArgumentParser(
        description="Agent zadaniowy hub.ag3nts.org",
        usage="python agent [-i] <plik_zadania.md>",
    )
    parser.add_argument("task_file", help="Plik .md z treścią zadania")
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Tryb interaktywny: agent prezentuje planowany krok przed wykonaniem",
    )
    args = parser.parse_args()

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
