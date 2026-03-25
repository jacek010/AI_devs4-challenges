import tiktoken
import workspace as ws


def count_tokens(text: str, model: str = "gpt-4o") -> str:
    """
    Zlicza tokeny w podanym tekście dla wskazanego modelu.
    Zwraca liczbę tokenów jako string.
    """
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("o200k_base")

    tokens = enc.encode(text)
    result = str(len(tokens))
    ws.log("COUNT_TOKENS", f"model={model} chars={len(text)}", result)
    return result


def truncate_to_tokens(text: str, max_tokens: int, model: str = "gpt-4o") -> str:
    """
    Przycina tekst do podanej maksymalnej liczby tokenów.
    Zwraca skrócony tekst.
    """
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("o200k_base")

    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return text

    truncated = enc.decode(tokens[:max_tokens])
    ws.log(
        "TRUNCATE_TO_TOKENS",
        f"model={model} original={len(tokens)} max={max_tokens}",
        f"truncated to {max_tokens} tokens",
    )
    return truncated


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "count_tokens",
            "description": (
                "Zlicza liczbę tokenów w podanym tekście dla danego modelu OpenAI. "
                "Przydatne do sprawdzenia czy tekst zmieści się w oknie kontekstu."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Tekst do zliczenia tokenów"},
                    "model": {
                        "type": "string",
                        "default": "gpt-4o",
                        "description": "Nazwa modelu OpenAI (np. gpt-4o, gpt-4, gpt-3.5-turbo)",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "truncate_to_tokens",
            "description": (
                "Przycina tekst do maksymalnej liczby tokenów. "
                "Użyj gdy tekst jest za długi dla modelu lub kontekstu."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Tekst do przycięcia"},
                    "max_tokens": {
                        "type": "integer",
                        "description": "Maksymalna liczba tokenów",
                    },
                    "model": {
                        "type": "string",
                        "default": "gpt-4o",
                        "description": "Nazwa modelu OpenAI (np. gpt-4o, gpt-4, gpt-3.5-turbo)",
                    },
                },
                "required": ["text", "max_tokens"],
            },
        },
    },
]
