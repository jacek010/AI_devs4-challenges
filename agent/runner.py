import json
from openai import AzureOpenAI
import config
import workspace as ws
from prompts import SYSTEM_PROMPT
from tools import TOOLS, TOOL_MAP


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

    log(f"\n🗂  Workspace : {ws.root()}/")
    log(f"🤖 Model     : {config.AZURE_DEPLOYMENT}")
    log(f"🔧 Narzędzia : {', '.join(TOOL_MAP.keys())}\n")

    for i in range(1, config.MAX_ITERATIONS + 1):
        log(f"{'─' * 55}")
        log(f"  Iteracja {i} / {config.MAX_ITERATIONS}")
        log(f"{'─' * 55}")

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
            log(f"\n💬 {msg.content}")

        # Agent skończył — brak wywołań narzędzi
        if not msg.tool_calls:
            log("\n✅ Agent zakończył pracę.")
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

    log("⚠️  Osiągnięto limit iteracji.")
    ws.log("LIMIT", f"Osiągnięto MAX_ITERATIONS={config.MAX_ITERATIONS}")
    return None


def _call_tool(name: str, args: dict, log) -> str:
    """Wywołuje narzędzie, loguje wywołanie i zwraca wynik jako string."""
    log(f"\n🔧 {name}()")
    for k, v in args.items():
        v_str = str(v)
        log(f"   {k}: {v_str[:120]}{'…' if len(v_str) > 120 else ''}")

    fn = TOOL_MAP.get(name)
    if fn is None:
        result = f"UNKNOWN_TOOL: {name}"
    else:
        try:
            result = fn(**args)
        except Exception as e:
            result = f"TOOL_ERROR [{name}]: {e}"

    r_str = str(result)
    log(f"   → {r_str[:300]}{'…' if len(r_str) > 300 else ''}")
    return r_str
