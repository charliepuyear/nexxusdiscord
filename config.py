import os
from pathlib import Path
from dotenv import load_dotenv

# Only load .env file if it exists (local dev). On Railway, env vars are set directly.
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
GOOGLE_CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json")
ADMIN_ROLE = os.environ.get("ADMIN_ROLE", "Mods")

# Debug: print whether token was found (without revealing it)
print(f"DISCORD_TOKEN loaded: {DISCORD_TOKEN is not None}")

# Default timeslots — admins can override per event
DEFAULT_TIMESLOTS = [
    "Slot 1 - Friday Evening",
    "Slot 2 - Saturday Morning",
    "Slot 3 - Saturday Afternoon",
    "Slot 4 - Saturday Evening",
    "Slot 5 - Sunday Morning",
    "Slot 6 - Sunday Afternoon",
]
