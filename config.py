import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
ADMIN_ROLE = os.getenv("ADMIN_ROLE", "Mods")

# Default timeslots — admins can override per event
DEFAULT_TIMESLOTS = [
    "Slot 1 - Friday Evening",
    "Slot 2 - Saturday Morning",
    "Slot 3 - Saturday Afternoon",
    "Slot 4 - Saturday Evening",
    "Slot 5 - Sunday Morning",
    "Slot 6 - Sunday Afternoon",
]
