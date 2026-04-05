"""Google Sheets integration for storing events and signups."""
from __future__ import annotations

import json
import os
import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Headers for each sheet
EVENT_HEADERS = [
    "Event Name", "Classes", "Cars", "Timeslots", "Deadline",
    "Status", "Created By", "Created At",
]
SIGNUP_HEADERS = [
    "Event Name", "Discord User", "Discord ID", "Primary Class",
    "Secondary Class", "Cars", "Available Timeslots", "Preferred Timeslot",
    "Signed Up At",
]


def get_client() -> gspread.Client:
    """Authenticate and return a gspread client.

    Supports either a credentials JSON file or a GOOGLE_CREDENTIALS_JSON
    environment variable containing the JSON string directly.
    """
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
        )
    return gspread.authorize(creds)


def get_spreadsheet() -> gspread.Spreadsheet:
    """Get the main spreadsheet."""
    client = get_client()
    return client.open_by_key(GOOGLE_SHEET_ID)


def ensure_worksheets():
    """Create the Events, Signups, and Config worksheets if they don't exist."""
    spreadsheet = get_spreadsheet()
    existing = [ws.title for ws in spreadsheet.worksheets()]

    if "Events" not in existing:
        ws = spreadsheet.add_worksheet(title="Events", rows=100, cols=len(EVENT_HEADERS))
        ws.append_row(EVENT_HEADERS)
        ws.format("1", {"textFormat": {"bold": True}})

    if "Signups" not in existing:
        ws = spreadsheet.add_worksheet(title="Signups", rows=1000, cols=len(SIGNUP_HEADERS))
        ws.append_row(SIGNUP_HEADERS)
        ws.format("1", {"textFormat": {"bold": True}})

    if "Config" not in existing:
        ws = spreadsheet.add_worksheet(title="Config", rows=50, cols=2)
        ws.append_row(["Key", "Value"])
        ws.format("1", {"textFormat": {"bold": True}})

    # Remove default Sheet1 if our sheets exist
    existing = [ws.title for ws in spreadsheet.worksheets()]
    if "Sheet1" in existing and len(existing) > 1:
        try:
            spreadsheet.del_worksheet(spreadsheet.worksheet("Sheet1"))
        except Exception:
            pass


# ── Event operations ──


def add_event(name: str, classes: list[str], cars: list[str],
              timeslots: list[str], deadline: str, created_by: str) -> bool:
    """Add a new event. Returns False if event name already exists."""
    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet("Events")

    # Check for duplicate name
    existing_events = ws.col_values(1)[1:]  # skip header
    if name in existing_events:
        return False

    from datetime import datetime
    ws.append_row([
        name,
        ", ".join(classes),
        ", ".join(cars),
        ", ".join(timeslots),
        deadline,
        "Open",
        created_by,
        datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    ])
    return True


def get_event(name: str) -> dict | None:
    """Get an event by name."""
    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet("Events")
    records = ws.get_all_records()
    for record in records:
        if record["Event Name"] == name:
            return record
    return None


def get_open_events() -> list[dict]:
    """Get all events with status 'Open'."""
    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet("Events")
    records = ws.get_all_records()
    return [r for r in records if r["Status"] == "Open"]


def get_all_events() -> list[dict]:
    """Get all events."""
    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet("Events")
    return ws.get_all_records()


def close_event(name: str) -> bool:
    """Close an event (no more signups). Returns False if not found."""
    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet("Events")
    events = ws.col_values(1)
    for i, event_name in enumerate(events):
        if event_name == name:
            ws.update_cell(i + 1, 6, "Closed")  # Column 6 = Status
            return True
    return False


def delete_event(name: str) -> bool:
    """Delete an event and all its signups."""
    spreadsheet = get_spreadsheet()

    # Delete from Events sheet
    ws_events = spreadsheet.worksheet("Events")
    events = ws_events.col_values(1)
    found = False
    for i, event_name in enumerate(events):
        if event_name == name:
            ws_events.delete_rows(i + 1)
            found = True
            break

    if not found:
        return False

    # Delete related signups
    ws_signups = spreadsheet.worksheet("Signups")
    signups = ws_signups.col_values(1)
    rows_to_delete = [i + 1 for i, e in enumerate(signups) if e == name and i > 0]
    for row in reversed(rows_to_delete):  # delete from bottom up
        ws_signups.delete_rows(row)

    return True


def update_event(name: str, classes: list[str] = None, cars: list[str] = None,
                 timeslots: list[str] = None, deadline: str = None) -> bool:
    """Update event fields. Returns False if not found."""
    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet("Events")
    events = ws.col_values(1)
    for i, event_name in enumerate(events):
        if event_name == name:
            row = i + 1
            if classes is not None:
                ws.update_cell(row, 2, ", ".join(classes))
            if cars is not None:
                ws.update_cell(row, 3, ", ".join(cars))
            if timeslots is not None:
                ws.update_cell(row, 4, ", ".join(timeslots))
            if deadline is not None:
                ws.update_cell(row, 5, deadline)
            return True
    return False


# ── Signup operations ──


def add_signup(event_name: str, discord_user: str, discord_id: str,
               primary_class: str, secondary_class: str, cars: str,
               available_timeslots: str, preferred_timeslot: str) -> bool:
    """Add a signup. Returns False if user already signed up for this event."""
    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet("Signups")

    # Check for existing signup
    records = ws.get_all_records()
    for record in records:
        if record["Event Name"] == event_name and str(record["Discord ID"]) == str(discord_id):
            return False

    from datetime import datetime
    ws.append_row([
        event_name,
        discord_user,
        str(discord_id),
        primary_class,
        secondary_class,
        cars,
        available_timeslots,
        preferred_timeslot,
        datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    ])
    return True


def update_signup(event_name: str, discord_id: str, primary_class: str,
                  secondary_class: str, cars: str, available_timeslots: str,
                  preferred_timeslot: str) -> bool:
    """Update an existing signup. Returns False if not found."""
    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet("Signups")
    records = ws.get_all_records()
    for i, record in enumerate(records):
        if record["Event Name"] == event_name and str(record["Discord ID"]) == str(discord_id):
            row = i + 2  # +1 for header, +1 for 0-index
            from datetime import datetime
            ws.update(f"D{row}:I{row}", [[
                primary_class,
                secondary_class,
                cars,
                available_timeslots,
                preferred_timeslot,
                datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            ]])
            return True
    return False


def cancel_signup(event_name: str, discord_id: str) -> bool:
    """Cancel a signup. Returns False if not found."""
    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet("Signups")
    records = ws.get_all_records()
    for i, record in enumerate(records):
        if record["Event Name"] == event_name and str(record["Discord ID"]) == str(discord_id):
            ws.delete_rows(i + 2)  # +1 for header, +1 for 0-index
            return True
    return False


def get_signups_for_event(event_name: str) -> list[dict]:
    """Get all signups for a specific event."""
    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet("Signups")
    records = ws.get_all_records()
    return [r for r in records if r["Event Name"] == event_name]


def get_user_signups(discord_id: str) -> list[dict]:
    """Get all signups for a specific user."""
    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet("Signups")
    records = ws.get_all_records()
    return [r for r in records if str(r["Discord ID"]) == str(discord_id)]


def get_user_signup_for_event(event_name: str, discord_id: str) -> dict | None:
    """Get a specific user's signup for a specific event."""
    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet("Signups")
    records = ws.get_all_records()
    for record in records:
        if record["Event Name"] == event_name and str(record["Discord ID"]) == str(discord_id):
            return record
    return None


# ── Channel management ──


def get_signup_channels() -> list[int]:
    """Get list of allowed signup channel IDs from Config sheet."""
    try:
        spreadsheet = get_spreadsheet()
        ws = spreadsheet.worksheet("Config")
        records = ws.get_all_records()
        for record in records:
            if record["Key"] == "signup_channels":
                value = str(record["Value"]).strip()
                if not value:
                    return []
                return [int(ch.strip()) for ch in value.split(",") if ch.strip()]
    except Exception:
        pass
    return []


def add_signup_channel(channel_id: int) -> bool:
    """Add a channel to the allowed signup channels list."""
    channels = get_signup_channels()
    if channel_id in channels:
        return False
    channels.append(channel_id)
    _save_signup_channels(channels)
    return True


def remove_signup_channel(channel_id: int) -> bool:
    """Remove a channel from the allowed signup channels list."""
    channels = get_signup_channels()
    if channel_id not in channels:
        return False
    channels.remove(channel_id)
    _save_signup_channels(channels)
    return True


def _save_signup_channels(channels: list[int]):
    """Save the signup channels list to the Config sheet."""
    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet("Config")
    records = ws.get_all_records()
    value = ", ".join(str(ch) for ch in channels)
    for i, record in enumerate(records):
        if record["Key"] == "signup_channels":
            ws.update_cell(i + 2, 2, value)
            return
    # Key doesn't exist yet, add it
    ws.append_row(["signup_channels", value])
