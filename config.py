import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SEED_KEYWORDS_ENDPOINT = os.getenv("SEED_KEYWORDS_ENDPOINT", "https://twebbackend-production.up.railway.app/api/keywords")
UPUP_AUTH_STATE = os.getenv("UPUP_AUTH_STATE", "./cache/auth_state.json")

JACCARD_THRESHOLD = 0.30
TOP_COMPETITORS = 10
DEFAULT_COUNTRY = 24
DEFAULT_MARKET = 1

APPS = [
    {
        "adam_id": "6746982805",
        "countries": ["RO", "JP", "HU", "KR", "BR"],
    },
]

CACHE_DB_PATH = "./cache/keywords.sqlite"
KEYWORD_CACHE_TTL_HOURS = 24
