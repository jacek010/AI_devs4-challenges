"""
Bazowa klasa SubagentRunner — izolowana pętla agenta dla subagentów.

Każdy subagent posiada:
- własny system prompt
- własny, ograniczony zestaw narzędzi
- izolowaną historię wiadomości (niewidoczną dla głównego agenta)
- osobny limit iteracji
"""

import json
from openai import AzureOpenAI
import config

# ─── Kolory ANSI (przyciemnione względem głównego agenta) ──────
_R  = "\033[0m"
_B  = "\033[1m"
_CY = "\033[0;36m"   # cyan
_YL = "\033[0;33m"   # yellow
_MG = "\033[0;35m"   # magenta
_GR = "\033[0;32m"   # green
_RE = "\033[0;31m"   # red


class SubagentRunner:
    """
    Izolowana pętla agenta dla subagentów.

    Parametry:
        system_prompt     — instrukcja systemowa specyficzna dla subagenta
        tool_definitions  — lista definicji narzędzi OpenAI (JSON Schema)
        tool_map          — słownik {nazwa: callable} dostępnych narzędzi
        name              — nazwa subagenta (do logowania)
        max_iterations    — maksymalna liczba iteracji (domyślnie 15)
        verbose           — czy wypisywać logi do stdout
    """

    def __init__(
        self,
        system_prompt: str,
        tool_definitions: list[dict],
        tool_map: dict,
        name: str = "subagent",
        max_iterations: int = 15,
        verbose: bool = True,
    ):
        self.system_prompt = system_prompt
        self.tool_definitions = tool_definitions
        self.tool_map = tool_map
        self.name = name
        self.max_iterations = max_iterations
        self.verbose = verbose

        self._client = AzureOpenAI(
            azure_endpoint=config.AZURE_ENDPOINT,
            api_key=config.AZURE_API_KEY,
            api_version=config.AZURE_API_VER,
        )

    # ──────────────────────────────────────────────────────────
    # Wewnętrzne metody pomocnicze
    # ──────────────────────────────────────────────────────────

    def _log(self, *args) -> None:
        if self.verbose:
            print(*args)

    def _call_tool(self, name: str, args: dict) -> str:
        """Wywołuje narzędzie i zwraca wynik jako string."""
        self._log(f"\n{_MG}  ┌{'─' * 50}┐{_R}")
        self._log(f"{_MG}  │  [{self.name}] 🔧 {_B}{name}{_R}{_MG}(){_R}")
        for k, v in args.items():
            self._log(f"{_MG}  │     {k}: {str(v)[:200]}{_R}")
        self._log(f"{_MG}  └{'─' * 50}┘{_R}")

        fn = self.tool_map.get(name)
        if fn is None:
            result = f"UNKNOWN_TOOL: {name}"
        else:
            try:
                result = fn(**args)
            except Exception as e:
                result = f"TOOL_ERROR [{name}]: {e}"

        r_str = str(result)
        err = r_str.startswith((
            "UNKNOWN_TOOL", "TOOL_ERROR",
            "IMAGE_FETCH_ERROR", "VISION_ERROR", "PYTHON_EVAL_ERROR",
        ))
        res_color = _RE if err else _GR
        display = r_str[:600] + ("…[skrócono]" if len(r_str) > 600 else "")

        self._log(f"\n{res_color}  ┌{'─' * 50}┐{_R}")
        self._log(f"{res_color}  │  [{self.name}] 📥 Wynik: {_B}{name}{_R}")
        for line in display.splitlines():
            self._log(f"{res_color}  │  {line}{_R}")
        self._log(f"{res_color}  └{'─' * 50}┘{_R}")

        return r_str

    # ──────────────────────────────────────────────────────────
    # Główna pętla
    # ──────────────────────────────────────────────────────────

    def run(self, task: str) -> str:
        """
        Uruchamia izolowaną pętlę subagenta dla podanego zadania.
        Zwraca końcową odpowiedź jako string.
        Historia wiadomości jest całkowicie izolowana od głównego agenta.
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user",   "content": task},
        ]

        self._log(f"\n{_CY}  ╔{'═' * 53}╗{_R}")
        self._log(f"{_CY}  ║  🤖 SUBAGENT: {self.name.upper():<38}║{_R}")
        self._log(f"{_CY}  ║  Narzędzia: {', '.join(self.tool_map.keys()):<40}║{_R}")
        self._log(f"{_CY}  ╚{'═' * 53}╝{_R}")

        for i in range(1, self.max_iterations + 1):
            self._log(f"\n{_CY}    ── [{self.name}] iteracja {i}/{self.max_iterations} ──{_R}")

            response = self._client.chat.completions.create(
                model=config.AZURE_DEPLOYMENT,
                messages=messages,
                tools=self.tool_definitions,
                tool_choice="auto",
                temperature=config.LLM_TEMPERATURE,
                max_tokens=config.LLM_MAX_TOKENS,
            )

            msg = response.choices[0].message
            messages.append(msg)

            if msg.content:
                preview = msg.content[:400] + ("…" if len(msg.content) > 400 else "")
                self._log(f"\n{_YL}  [{self.name}] 💬 {preview}{_R}")

            # Subagent zakończył pracę
            if not msg.tool_calls:
                self._log(f"\n{_GR}  [{self.name}] ✅ Zakończył pracę po {i} iteracjach.{_R}")
                return msg.content or "(subagent nie zwrócił treści odpowiedzi)"

            # Wywołaj narzędzia
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                tool_args = json.loads(tc.function.arguments)
                tool_result = self._call_tool(tool_name, tool_args)
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      tool_result,
                })

        self._log(f"\n{_RE}  [{self.name}] ⚠️  Osiągnięto limit iteracji ({self.max_iterations}).{_R}")
        return (
            f"SUBAGENT_LIMIT_REACHED: subagent '{self.name}' przekroczył limit "
            f"{self.max_iterations} iteracji bez zwrócenia końcowej odpowiedzi."
        )
