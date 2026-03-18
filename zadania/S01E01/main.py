import csv
import io
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from AI_devs4 root
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Make utils/ importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.Hub_Connector import HubConnector
from utils.LLM_Connector import AzureOpenAIConnector

CURRENT_YEAR = 2026
MIN_AGE = 20
MAX_AGE = 40
REQUIRED_GENDER = "M"
REQUIRED_CITY = "Grudziądz"

TAGS = ["IT", "transport", "edukacja", "medycyna", "praca z ludźmi", "praca z pojazdami", "praca fizyczna"]

TAG_DESCRIPTIONS = """
Dostępne tagi i ich zakresy:
- IT: programiści, administratorzy sieci, specjaliści IT, inżynierowie oprogramowania, analitycy systemów
- transport: kierowcy, spedytorzy, logistycy, kurierzy, maszyniści, operatorzy floty, dysponenci transportu
- edukacja: nauczyciele, wykładowcy, trenerzy, instruktorzy, edukatorzy
- medycyna: lekarze, pielęgniarki, ratownicy medyczni, farmaceuci, fizjoterapeuci, pracownicy służby zdrowia
- praca z ludźmi: sprzedawcy, obsługa klienta, handlowcy, pracownicy socjalni, psycholodzy, menadżerowie
- praca z pojazdami: mechanicy, serwisanci pojazdów, kierowcy (każdy kto prowadzi pojazd), operatorzy maszyn
- praca fizyczna: pracownicy budowlani, magazynierzy, robotnicy, operatorzy wózków widłowych, monterzy
"""

TAGGING_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "job_tags",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "tags": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "enum": TAGS
                                }
                            }
                        },
                        "required": ["id", "tags"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["results"],
            "additionalProperties": False
        }
    }
}


def fetch_people_csv(hub: HubConnector) -> list[dict]:
    response = hub.receive_data("/people.csv")
    text = response.content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _birth_year(person: dict) -> int:
    """Extract year from birthDate field (e.g. '1990-05-15' or '1990')."""
    raw = (person.get("birthDate") or "").strip()
    if not raw:
        return 0
    return int(raw.split("-")[0])


def filter_people(people: list[dict]) -> list[dict]:
    filtered = []
    for person in people:
        try:
            born = _birth_year(person)
            age = CURRENT_YEAR - born
        except (ValueError, TypeError):
            continue

        gender = (person.get("gender") or "").strip()
        city = (person.get("birthPlace") or "").strip()

        if gender == REQUIRED_GENDER and city == REQUIRED_CITY and MIN_AGE <= age <= MAX_AGE:
            filtered.append(person)

    return filtered


def tag_jobs(people: list[dict], llm: AzureOpenAIConnector) -> dict[int, list[str]]:
    if not people:
        return {}

    job_lines = "\n".join(
        f"{i}. {person.get('job', '').strip()}"
        for i, person in enumerate(people)
    )

    system_message = (
        "Jesteś ekspertem klasyfikacji zawodów. "
        "Przypisz każdemu stanowisku jeden lub więcej tagów z listy. "
        "Możesz przypisać wiele tagów, jeśli stanowisko pasuje do kilku kategorii.\n\n"
        f"{TAG_DESCRIPTIONS}"
    )

    user_message = (
        "Poniżej lista numerowanych opisów stanowisk pracy. "
        "Przypisz odpowiednie tagi do każdego stanowiska.\n\n"
        f"{job_lines}"
    )

    raw = llm.chat_completion(
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        temperature=0,
        max_tokens=2000,
        response_format=TAGGING_SCHEMA,
    )

    data = json.loads(raw)
    return {item["id"]: item["tags"] for item in data["results"]}


def build_answer(people: list[dict], tags_map: dict[int, list[str]]) -> list[dict]:
    answer = []
    for i, person in enumerate(people):
        tags = tags_map.get(i, [])
        if "transport" not in tags:
            continue
        answer.append({
            "name": person.get("name", "").strip(),
            "surname": person.get("surname", "").strip(),
            "gender": person.get("gender", "").strip(),
            "born": _birth_year(person),
            "city": (person.get("birthPlace") or "").strip(),
            "tags": tags,
        })
    return answer


def main():
    hub = HubConnector()
    llm = AzureOpenAIConnector()

    print("Pobieranie people.csv...")
    people = fetch_people_csv(hub)
    print(f"  Liczba wierszy: {len(people)}")
    if people:
        print(f"  Kolumny: {list(people[0].keys())}")

    print("Filtrowanie...")
    filtered = filter_people(people)
    print(f"  Spełnia kryteria: {len(filtered)} osób")
    for p in filtered:
        print(f"    {p.get('name')} {p.get('surname')} | born={p.get('birthDate')} | job={p.get('job')}")

    if not filtered:
        print("Brak pasujących osób. Przerywam.")
        return

    print("Tagowanie zawodów przez LLM...")
    tags_map = tag_jobs(filtered, llm)
    print("  Wyniki tagowania:")
    for i, person in enumerate(filtered):
        print(f"    [{i}] {person.get('job')} → {tags_map.get(i, [])}")

    answer = build_answer(filtered, tags_map)
    print(f"\nOsoby z tagiem 'transport': {len(answer)}")
    for a in answer:
        print(f"  {a['name']} {a['surname']} | tags={a['tags']}")

    print("\nWysyłanie odpowiedzi...")
    result = hub.verify("people", answer)
    print(f"Odpowiedź z serwera: {result}")
    
    with open("answer.json", "w", encoding="utf-8") as f:
        json.dump(answer, f, indent=2, ensure_ascii=False)
    print("Odpowiedź zapisana do answer.json")


if __name__ == "__main__":
    main()
