import json
from openai import AzureOpenAI
import config
import workspace as ws
from prompts import SYSTEM_PROMPT
from tools import TOOLS, TOOL_MAP

# ─── Kolory ANSI ──────────────────────────────────────────────
_R  = "\033[0m"       # reset
_B  = "\033[1m"       # bold
_CY = "\033[1;36m"    # bold cyan   — nagłówki iteracji
_YL = "\033[1;33m"    # bold yellow — decyzja / reasoning agenta
_MG = "\033[1;35m"    # bold magenta— wywołanie narzędzia
_GR = "\033[1;32m"    # bold green  — odpowiedź systemu / wynik
_BL = "\033[1;34m"    # bold blue   — sleep
_RE = "\033[1;31m"    # bold red    — błędy


def run(task_text: str, verbose: bool = True) -> str | None:
    """
    Główna pętla agenta. Przyjmuje treść zadania i wykonuje je do końca.
    Zwraca ostatnią wiadomość agenta.
    """
    client = AzureOpenAI(
        azure_endpoint=config.AZURE_ENDPOINT,
        api_key=config.AZURE_API_KEY,
        api_version=config.AZURE_API_VER,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": f"Workspace gotowy. Treść zadania:\n\n{task_text}"},
    ]

    def log(*args):
        if verbose:
            print(*args)

    log(f"\n{_CY}🗂  Workspace : {ws.root()}/{_R}")
    log(f"{_CY}🤖 Model     : {config.AZURE_DEPLOYMENT}{_R}")
    log(f"{_CY}🔧 Narzędzia : {', '.join(TOOL_MAP.keys())}{_R}\n")

    for i in range(1, config.MAX_ITERATIONS + 1):
        log(f"\n{_CY}{'═' * 55}{_R}")
        log(f"{_CY}  Iteracja {i} / {config.MAX_ITERATIONS}{_R}")
        log(f"{_CY}{'═' * 55}{_R}")

        response = client.chat.completions.create(
            model=config.AZURE_DEPLOYMENT,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=config.LLM_TEMPERATURE,
            max_tokens=config.LLM_MAX_TOKENS,
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

        # Agent skończył — brak wywołań narzędzi
        if not msg.tool_calls:
            log(f"\n{_GR}{'─' * 55}{_R}")
            log(f"{_GR}  ✅ Agent zakończył pracę.{_R}")
            log(f"{_GR}{'─' * 55}{_R}")
            ws.log("DONE", msg.content or "(brak wiadomości końcowej)")
            return msg.content

        # Wykonaj narzędzia
        for tc in msg.tool_calls:
            name   = tc.function.name
            args   = json.loads(tc.function.arguments)
            result = _call_tool(name, args, log)

            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      str(result),
            })

    log(f"\n{_RE}⚠️  Osiągnięto limit iteracji ({config.MAX_ITERATIONS}).{_R}")
    ws.log("LIMIT", f"Osiągnięto MAX_ITERATIONS={config.MAX_ITERATIONS}")
    return None


def _call_tool(name: str, args: dict, log) -> str:
    """Wywołuje narzędzie, loguje wywołanie i zwraca wynik jako string."""
    is_sleep = (name == "sleep")
    color = _BL if is_sleep else _MG

    log(f"\n{color}┌{'─' * 53}┐{_R}")
    log(f"{color}│  🔧 Narzędzie: {_B}{name}{_R}{color}(){_R}")
    for k, v in args.items():
        v_str = str(v)
        log(f"{color}│     {k}: {v_str[:120]}{'…' if len(v_str) > 120 else ''}{_R}")
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
