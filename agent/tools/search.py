# tools/search.py
import workspace as ws

def web_search(query: str) -> str:
    """Wyszukuje w internecie i zwraca wyniki."""
    ...
    ws.log("WEB_SEARCH", query, result)
    return result

DEFINITIONS = [{
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Wyszukuje informacje w internecie.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}]
