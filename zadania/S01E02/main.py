import json
import math
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from AI_devs4 root
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Make utils/ importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.Hub_Connector import HubConnector
from utils.LLM_Connector import AzureOpenAIConnector


# ── Haversine formula ──────────────────────────────────────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in km between two GPS points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


# ── Coordinate resolution via LLM ─────────────────────────────────────────────

def get_city_coords(llm: AzureOpenAIConnector, cities: list) -> dict:
    prompt = (
        "Return ONLY a valid JSON object (no markdown, no explanation) mapping each city name "
        "to its approximate GPS coordinates as {\"lat\": float, \"lng\": float}.\n"
        f"Cities: {cities}\n"
        "Example format: {\"Warsaw\": {\"lat\": 52.23, \"lng\": 21.01}}"
    )
    raw = llm.simple_prompt(prompt, temperature=0, max_tokens=500)
    raw = re.sub(r"```[a-z]*\n?", "", raw).strip().rstrip("`")
    return json.loads(raw)


# ── Tool implementations ───────────────────────────────────────────────────────

def _extract_locations(api_result) -> list:
    """Normalize various API response shapes to a flat list of location dicts."""
    if isinstance(api_result, list):
        return api_result
    if isinstance(api_result, dict):
        for key in ("locations", "data", "message", "result", "answer"):
            val = api_result.get(key)
            if isinstance(val, list):
                return val
    return []


def _parse_coord(loc: dict, keys: tuple):
    """Return the first non-None value found among the given keys."""
    for k in keys:
        v = loc.get(k)
        if v is not None:
            return float(v)
    return None


def get_person_closest_plant_impl(
    hub: HubConnector,
    power_plants_with_coords: dict,
    name: str,
    surname: str,
) -> dict:
    raw = hub.api_post_request("/location", {"name": name, "surname": surname})
    locations = _extract_locations(raw)

    if not locations:
        return {
            "error": f"No locations returned for {name} {surname}",
            "raw_response": str(raw)[:300],
        }

    best_dist = float("inf")
    best_plant = None
    best_coords = None

    for loc in locations:
        lat = _parse_coord(loc, ("lat", "latitude", "gps_lat"))
        lon = _parse_coord(loc, ("lon", "lng", "longitude", "gps_lon", "gps_lng"))
        if lat is None or lon is None:
            continue
        for city, info in power_plants_with_coords.items():
            d = haversine(lat, lon, info["lat"], info["lng"])
            if d < best_dist:
                best_dist = d
                best_plant = {"city": city, "code": info["code"]}
                best_coords = {"lat": lat, "lon": lon}

    if best_plant is None:
        return {
            "error": "Could not parse any lat/lon from location entries",
            "sample": str(locations[:2]),
        }

    return {
        "name": name,
        "surname": surname,
        "min_distance_km": round(best_dist, 2),
        "nearest_plant": best_plant,
        "best_location": best_coords,
    }


def get_access_level_impl(hub: HubConnector, name: str, surname: str, birthYear: int) -> dict:
    raw = hub.api_post_request("/accesslevel", {"name": name, "surname": surname, "birthYear": birthYear})
    # Normalise various response shapes
    if isinstance(raw, dict):
        for key in ("accessLevel", "access_level", "level", "data", "message", "answer", "result"):
            val = raw.get(key)
            if val is not None:
                return {"accessLevel": val}
        return {"accessLevel": raw}  # pass full dict so agent can inspect
    return {"accessLevel": raw}


def submit_answer_impl(
    hub: HubConnector,
    name: str,
    surname: str,
    access_level,
    power_plant_code: str,
) -> dict:
    answer = {
        "name": name,
        "surname": surname,
        "accessLevel": access_level,
        "powerPlant": power_plant_code,
    }
    return hub.verify("findhim", answer)


# ── OpenAI Function Calling — tool schemas ─────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_person_closest_plant",
            "description": (
                "Fetch all historical GPS locations for a suspect and compute the minimum "
                "Haversine distance to any power plant. Returns nearest plant city, its code, "
                "and the minimum distance in km."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "First name of the suspect"},
                    "surname": {"type": "string", "description": "Surname of the suspect"},
                },
                "required": ["name", "surname"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_access_level",
            "description": "Fetch the access level for a suspect from /api/accesslevel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "First name of the suspect"},
                    "surname": {"type": "string", "description": "Surname of the suspect"},
                    "birthYear": {"type": "integer", "description": "Birth year of the suspect"},
                },
                "required": ["name", "surname", "birthYear"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_answer",
            "description": (
                "Submit the final answer to /verify. Call this ONLY after you have determined "
                "the suspect with the smallest min_distance_km AND retrieved their accessLevel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "First name of the suspect"},
                    "surname": {"type": "string", "description": "Surname of the suspect"},
                    "accessLevel": {
                        "description": "Access level value returned by get_access_level"
                    },
                    "powerPlant": {
                        "type": "string",
                        "description": "Power plant code from nearest_plant.code (e.g. PWR1234PL)",
                    },
                },
                "required": ["name", "surname", "accessLevel", "powerPlant"],
            },
        },
    },
]


# ── Agent dispatcher ───────────────────────────────────────────────────────────

def dispatch(tool_name: str, args: dict, hub: HubConnector, power_plants_with_coords: dict):
    if tool_name == "get_person_closest_plant":
        return get_person_closest_plant_impl(
            hub, power_plants_with_coords, args["name"], args["surname"]
        )
    if tool_name == "get_access_level":
        return get_access_level_impl(hub, args["name"], args["surname"], args["birthYear"])
    if tool_name == "submit_answer":
        return submit_answer_impl(
            hub,
            args["name"],
            args["surname"],
            args["accessLevel"],
            args["powerPlant"],
        )
    return {"error": f"Unknown tool: {tool_name}"}


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    hub = HubConnector()
    llm = AzureOpenAIConnector()

    with open("S01E01/answer.json", "r") as f:
        suspects = json.load(f)

    with open("S01E02/findhim_locations.json", "r") as f:
        locations_data = json.load(f)

    power_plants = locations_data["power_plants"]
    city_list = list(power_plants.keys())

    # ── Step 1: Resolve power plant coordinates via LLM ──────────────────────
    print("Fetching power plant coordinates from LLM...")
    city_coords = get_city_coords(llm, city_list)
    print(f"Received coords: {json.dumps(city_coords, ensure_ascii=False, indent=2)}")

    power_plants_with_coords = {}
    for city, info in power_plants.items():
        matched_key = next(
            (k for k in city_coords if k.lower() == city.lower() or city.lower() in k.lower()),
            None,
        )
        if matched_key:
            power_plants_with_coords[city] = {
                **info,
                "lat": city_coords[matched_key]["lat"],
                "lng": city_coords[matched_key]["lng"],
            }
        else:
            print(f"WARNING: no coordinates found for '{city}'")

    print(f"Plants with coords: {list(power_plants_with_coords.keys())}\n")

    # ── Step 2: Build agent messages ─────────────────────────────────────────
    suspects_json = json.dumps(
        [{"name": s["name"], "surname": s["surname"], "birthYear": s["born"]} for s in suspects],
        ensure_ascii=False,
    )

    system_prompt = f"""You are an investigative agent. Your goal is to identify which suspect was geographically closest to any power plant.

Suspects to investigate:
{suspects_json}

Instructions:
1. Call get_person_closest_plant for EACH suspect in the list above (all {len(suspects)} of them).
2. Compare the min_distance_km values returned — identify the suspect with the SMALLEST value.
3. Call get_access_level for that suspect to retrieve their access level.
4. Call submit_answer with: name, surname, accessLevel (from step 3), and powerPlant code (from nearest_plant.code in step 2).

You MUST check every suspect before submitting."""

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": "Investigate all suspects and find who was closest to a power plant. Submit the answer when done.",
        },
    ]

    # ── Step 3: Agent loop ────────────────────────────────────────────────────
    MAX_ITER = 15
    print(f"Starting agent loop (max {MAX_ITER} iterations)...\n")

    for i in range(MAX_ITER):
        print(f"--- Iteration {i + 1} ---")
        response = llm.client.chat.completions.create(
            model=llm.deployment_name,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0,
            max_tokens=2000,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            print(f"\nAgent finished.\n{msg.content}")
            break

        # Append assistant message (serialised as plain dict for API compatibility)
        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)
            print(f"  → {fn_name}({fn_args})")
            result = dispatch(fn_name, fn_args, hub, power_plants_with_coords)
            print(f"  ← {result}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    else:
        print(f"\nWarning: reached maximum iterations ({MAX_ITER}) without finishing.")