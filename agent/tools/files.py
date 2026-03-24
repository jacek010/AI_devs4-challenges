import workspace as ws


def write_file(filename: str, content: str) -> str:
    """
    Zapisuje plik tekstowy do output/ w workspace.
    Używaj do zachowania deklaracji, wyników pośrednich przed wysłaniem.
    filename: sama nazwa pliku, np. 'declaration.txt'
    """
    path = ws.output_write(filename, content)
    ws.log("WRITE_FILE", f"output/{filename}", content)
    return f"Zapisano: {path}"


def read_file(filename: str) -> str:
    """
    Odczytuje wcześniej pobrany lub zapisany plik z workspace.
    Przeszukuje output/ i cache/. Obsługuje częściowe dopasowanie nazwy.
    """
    result = ws.find_file(filename)
    if result:
        ws.log("READ_FILE", filename, result)
        return result
    return f"FILE_NOT_FOUND: '{filename}' — sprawdź list_workspace() aby zobaczyć dostępne pliki."


def list_workspace() -> str:
    """
    Listuje pliki w workspace (cache/ i output/).
    Sprawdź na początku pracy — agent może wznawiać przerwaną sesję.
    """
    result = ws.ls()
    ws.log("LIST_WORKSPACE", result)
    return result


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Zapisuje plik tekstowy do output/ w workspace. "
                "Używaj do zachowania deklaracji i wyników pośrednich."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Odczytuje plik z workspace (output/ lub cache/). "
                "Obsługuje częściowe dopasowanie nazwy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_workspace",
            "description": (
                "Listuje pliki w workspace. "
                "Zawsze wywołaj na początku — część plików może być z poprzedniej sesji."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]
