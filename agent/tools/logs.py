"""
Narzędzie do filtrowania i kompresji dużych plików logów.
Niezbędne przy zadaniach wymagających analizy logów systemowych (np. zadanie 'failure').
"""
import re
import workspace as ws
import tiktoken

_SEVERITY_ORDER = {"DEBU": 0, "INFO": 1, "WARN": 2, "ERRO": 3, "CRIT": 4, "FATA": 4}
_SEVERITY_RE = re.compile(
    r'\[(DEBUG|INFO|NOTICE|WARN(?:ING)?|ERR(?:OR)?|CRIT(?:ICAL)?|FATAL)\]',
    re.IGNORECASE,
)


def _count_tokens(text: str) -> int:
    try:
        enc = tiktoken.get_encoding("o200k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


def _severity_rank(line: str) -> int:
    m = _SEVERITY_RE.search(line)
    if not m:
        return -1
    key = m.group(1).upper()[:4]
    return _SEVERITY_ORDER.get(key, -1)


def filter_log_file(
    filename: str,
    min_severity: str = "WARN",
    keywords: str = "",
    max_tokens: int = 1500,
) -> str:
    """
    Filtruje duży plik logów i kompresuje go do podanego limitu tokenów.

    Parametry:
    - filename: nazwa pliku w workspace (cache/ lub output/), obsługuje częściowe dopasowanie
    - min_severity: poziom ważności do filtrowania (WARN, ERRO/ERROR, CRIT, DEBUG, INFO).
      Domyślnie WARN — zwraca linie WARN, ERROR, CRIT i wyżej.
    - keywords: opcjonalne słowa kluczowe oddzielone spacją — filtruje tylko linie zawierające
      przynajmniej jedno z nich (wielkość liter bez znaczenia). Puste = bez filtra słów.
    - max_tokens: maksymalna liczba tokenów wynikowego tekstu (domyślnie 1500).
      Jeśli wynik jest za długi, usuwane są linie o niższym priorytecie.

    Zwraca:
    - Przefiltrowane linie logów oddzielone \\n
    - Statystyki: ile linii wejściowych, ile po filtrze, ile tokenów
    - Ostrzeżenie jeśli limit tokenów wymógł dalsze przycinanie
    """
    content = ws.find_file(filename)
    if not content:
        return f"FILE_NOT_FOUND: '{filename}' — sprawdź list_workspace() aby zobaczyć dostępne pliki."

    # Mapuj alias min_severity → rank
    sev_aliases = {
        "DEBUG": 0, "DEBU": 0,
        "INFO": 1,
        "WARN": 2, "WARNING": 2,
        "ERRO": 3, "ERROR": 3,
        "CRIT": 4, "CRITICAL": 4, "FATA": 4, "FATAL": 4,
    }
    min_rank = sev_aliases.get(min_severity.upper(), 2)

    kw_list = [k.strip().lower() for k in keywords.split() if k.strip()] if keywords else []

    all_lines = content.splitlines()
    total_input = len(all_lines)

    # Krok 1: filtr severity
    filtered = [ln for ln in all_lines if _severity_rank(ln) >= min_rank]

    # Krok 2: filtr słów kluczowych (OR — przynajmniej jedno pasuje)
    if kw_list:
        filtered = [ln for ln in filtered if any(kw in ln.lower() for kw in kw_list)]

    total_filtered = len(filtered)

    if not filtered:
        return (
            f"FILTER_RESULT: Brak linii spełniających kryteria.\n"
            f"  Wejście: {total_input} linii\n"
            f"  min_severity={min_severity}, keywords={keywords or '(brak)'}"
        )

    # Krok 3: sprawdź tokeny — jeśli za dużo, przytnij od dołu priorytetów
    result_text = "\n".join(filtered)
    tokens_now = _count_tokens(result_text)
    truncated = False
    removed_count = 0

    if tokens_now > max_tokens:
        # Sortuj według rangi (najważniejsze pierwsze), przycinaj do limitu
        ranked = sorted(filtered, key=lambda ln: -_severity_rank(ln))
        kept = []
        budget = max_tokens - 50  # zapas na nagłówek
        running_tokens = 0
        for ln in ranked:
            ln_tokens = _count_tokens(ln) + 1  # +1 za \n
            if running_tokens + ln_tokens > budget:
                break
            kept.append(ln)
            running_tokens += ln_tokens
        # Przywróć oryginalną kolejność chronologiczną
        kept_set = set(id(ln) for ln in kept)
        # Musimy zachować kolejność z filtered — iterujemy filtered i sprawdzamy
        kept_ordered = []
        kept_lines_set = set(kept)
        for ln in filtered:
            if ln in kept_lines_set:
                kept_ordered.append(ln)
                kept_lines_set.discard(ln)
        removed_count = total_filtered - len(kept_ordered)
        result_text = "\n".join(kept_ordered)
        tokens_now = _count_tokens(result_text)
        truncated = True

    ws.log(
        "FILTER_LOG_FILE",
        f"{filename} | wejście: {total_input} linii | po filtrze: {total_filtered} | "
        f"wynik: {len(result_text.splitlines())} linii | {tokens_now} tokenów",
    )

    header = (
        f"[FILTER_LOG: {filename} | wejście: {total_input} linii"
        f" | po filtrze ({min_severity}+{', kw: ' + keywords if kw_list else ''}): {total_filtered} linii"
        f" | wynik: ~{tokens_now} tokenów"
    )
    if truncated:
        header += f" | ⚠ przycięto {removed_count} linii niższego priorytetu aby zmieścić się w {max_tokens} tokenach"
    header += "]\n"

    return header + result_text


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "filter_log_file",
            "description": (
                "Filtruje duży plik logów systemowych i kompresuje go do podanego limitu tokenów. "
                "Używaj do zadań wymagających analizy logów — zamiast ładować cały plik do kontekstu, "
                "wyciągnij tylko zdarzenia WARN/ERROR/CRIT i zmieść się w limicie tokenów. "
                "Wynik zawiera przefiltrowane linie + statystyki."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Nazwa pliku logów w workspace (obsługuje częściowe dopasowanie).",
                    },
                    "min_severity": {
                        "type": "string",
                        "enum": ["DEBUG", "INFO", "WARN", "ERRO", "ERROR", "CRIT", "CRITICAL"],
                        "description": (
                            "Minimalny poziom ważności logów do uwzględnienia. "
                            "WARN = WARN + ERROR + CRIT. CRIT = tylko krytyczne. Domyślnie WARN."
                        ),
                    },
                    "keywords": {
                        "type": "string",
                        "description": (
                            "Opcjonalne słowa kluczowe oddzielone spacją — filtruj tylko linie "
                            "zawierające przynajmniej jedno z nich (np. 'pump coolant reactor'). "
                            "Puste = bez filtra słów kluczowych."
                        ),
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": (
                            "Maksymalna liczba tokenów wynikowego tekstu. "
                            "Domyślnie 1500. Gdy wynik jest za długi, usuwane są linie "
                            "o niższym priorytecie (zachowywane CRIT > ERROR > WARN)."
                        ),
                    },
                },
                "required": ["filename"],
            },
        },
    },
]
