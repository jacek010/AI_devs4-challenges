# tools/search.py
import urllib.parse
import requests
import workspace as ws


def web_search(query: str, max_results: int = 5) -> str:
    """
    Wyszukuje w internecie i zwraca wyniki z DuckDuckGo.
    max_results: maksymalna liczba wyników (1-10).
    """
    max_results = max(1, min(10, max_results))

    # DuckDuckGo Instant Answer API
    try:
        params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params=params,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; agent-bot/1.0)"},
        )
        data = resp.json()

        results = []

        # AbstractText — bezpośrednia odpowiedź (np. Wikipedia)
        if data.get("AbstractText"):
            source = data.get("AbstractSource", "")
            url = data.get("AbstractURL", "")
            results.append(f"[Odpowiedź bezpośrednia — {source}]\n{data['AbstractText']}\nURL: {url}")

        # Answer — krótka odpowiedź faktograficzna
        if data.get("Answer"):
            results.append(f"[Odpowiedź faktograficzna]\n{data['Answer']}")

        # RelatedTopics — powiązane tematy
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                url = topic.get("FirstURL", "")
                results.append(f"- {topic['Text']}\n  URL: {url}")

        if results:
            result = "\n\n".join(results)
            ws.log("WEB_SEARCH", query, result[:500])
            return result

    except Exception as e:
        ws.log("WEB_SEARCH_DDG_ERROR", query, str(e))

    # Fallback — DuckDuckGo HTML scraping
    try:
        encoded = urllib.parse.quote_plus(query)
        resp = requests.get(
            f"https://html.duckduckgo.com/html/?q={encoded}",
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        text = resp.text

        # Wyciąganie wyników z HTML (prosty parser bez BeautifulSoup)
        import re
        snippets = re.findall(
            r'<a class="result__snippet"[^>]*>(.*?)</a>',
            text,
            re.DOTALL,
        )
        links = re.findall(
            r'<a class="result__url"[^>]*>(.*?)</a>',
            text,
            re.DOTALL,
        )
        # Usuń tagi HTML z wyników
        def _strip(s):
            return re.sub(r"<[^>]+>", "", s).strip()

        entries = []
        for i, snippet in enumerate(snippets[:max_results]):
            url = _strip(links[i]) if i < len(links) else ""
            entries.append(f"{i+1}. {_strip(snippet)}\n   URL: {url}" if url else f"{i+1}. {_strip(snippet)}")

        if entries:
            result = f"Wyniki wyszukiwania dla: \"{query}\"\n\n" + "\n\n".join(entries)
            ws.log("WEB_SEARCH (html)", query, result[:500])
            return result

        result = f"WEB_SEARCH: brak wyników dla zapytania: {query!r}"
        ws.log("WEB_SEARCH_EMPTY", query)
        return result

    except Exception as e:
        result = f"WEB_SEARCH_ERROR: {e}"
        ws.log("WEB_SEARCH_ERROR", query, result)
        return result


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Wyszukuje informacje w internecie (DuckDuckGo). "
                "Zwraca wyniki tekstowe z URL-ami. "
                "Używaj gdy potrzebujesz aktualnych danych lub wiedzy spoza task.md."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Zapytanie wyszukiwania. Używaj angielskiego dla lepszych wyników.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Liczba wyników do zwrócenia (1-10, domyślnie 5).",
                    },
                },
                "required": ["query"],
            },
        },
    }
]
