import os

from dotenv import load_dotenv
load_dotenv()

# ─── Azure OpenAI ──────────────────────────────────────────────
AZURE_ENDPOINT   = os.environ["AZURE_OPENAI_ENDPOINT"]
AZURE_API_KEY    = os.environ["AZURE_OPENAI_KEY"]
AZURE_API_VER    = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
AZURE_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1")

# ─── Hub ag3nts.org ────────────────────────────────────────────
HUB_BASE_URL    = os.environ["AI_DEVS4_BASE_URL"]
HUB_API_KEY    = os.environ["AI_DEVS4_API_KEY"]
HUB_VERIFY_URL = "https://hub.ag3nts.org/verify"


# ─── Agent ────────────────────────────────────────────────────
MAX_ITERATIONS = 60
LLM_TEMPERATURE = 0.1
LLM_MAX_TOKENS  = 4096

# ─── Kompresja historii kontekstu ─────────────────────────────
CONTEXT_WINDOW       = 120_000  # zakładany limit okna modelu (tokeny)
COMPRESS_THRESHOLD   = 0.70     # kompresuj gdy historia przekroczy ten ułamek
COMPRESS_KEEP_RECENT = 14       # n ostatnich wiad. (non-system) zawsze zachowuj
