# Nexxus Esports - Race Signup Bot Setup Guide

## Prerequisites
- Python 3.10+
- A Discord server you have admin access to
- A Google account

---

## Step 1: Create a Discord Bot

1. Go to https://discord.com/developers/applications
2. Click **"New Application"** — name it something like "Nexxus Race Signups"
3. Go to the **Bot** tab on the left
4. Click **"Reset Token"** and copy the token — you'll need this for `.env`
5. Under **Privileged Gateway Intents**, enable:
   - **Server Members Intent**
   - **Message Content Intent**
6. Go to the **OAuth2** tab
7. Under **Scopes**, check `bot` and `applications.commands`
8. Under **Bot Permissions**, check:
   - Send Messages
   - Embed Links
   - Attach Files
   - Use Slash Commands
   - Read Message History
9. Copy the generated URL at the bottom and open it in your browser to invite the bot to your server

---

## Step 2: Set Up Google Sheets API

1. Go to https://console.cloud.google.com/
2. Create a new project (or use an existing one)
3. Enable these APIs:
   - **Google Sheets API**
   - **Google Drive API**
4. Go to **Credentials** > **Create Credentials** > **Service Account**
5. Name it whatever you want, click through the steps
6. Click on the service account you just created
7. Go to the **Keys** tab > **Add Key** > **Create new key** > **JSON**
8. Download the JSON file and save it as `credentials.json` in the bot's folder
9. **Important:** Copy the service account email (looks like `name@project.iam.gserviceaccount.com`)

---

## Step 3: Create and Share a Google Sheet

1. Create a new Google Sheet (https://sheets.new)
2. Copy the **Spreadsheet ID** from the URL:
   `https://docs.google.com/spreadsheets/d/`**THIS_PART**`/edit`
3. Click **Share** and add the service account email from Step 2 as an **Editor**
4. The bot will automatically create "Events" and "Signups" tabs when you run `/setup-sheets`

---

## Step 4: Configure the Bot

1. Copy `.env.example` to `.env`:
   ```
   cp .env.example .env
   ```

2. Fill in your `.env` file:
   ```
   DISCORD_TOKEN=your_bot_token_from_step_1
   GOOGLE_SHEET_ID=your_spreadsheet_id_from_step_3
   GOOGLE_CREDENTIALS_FILE=credentials.json
   SIGNUP_CHANNEL_ID=your_channel_id
   ADMIN_ROLE=Race Director
   ```

   To get a channel ID: Enable Developer Mode in Discord (Settings > Advanced), then right-click the channel > Copy ID.

---

## Step 5: Install and Run

```bash
pip install -r requirements.txt
python bot.py
```

---

## Step 6: First-Time Setup

1. Make sure you have a role called **"Race Director"** (or whatever you set `ADMIN_ROLE` to) in your Discord server
2. Run `/setup-sheets` in Discord — this creates the Events and Signups worksheets in your Google Sheet
3. You're ready to go!

---

## Commands

### Admin Commands (require the Admin Role)
| Command | Description |
|---------|-------------|
| `/create-event` | Opens a form to create a new race event |
| `/edit-event` | Edit an existing event's details |
| `/close-event` | Close signups for an event |
| `/delete-event` | Delete an event and all its signups |
| `/export-signups` | Export signups for an event as a CSV file |
| `/setup-sheets` | Initialize the Google Sheets worksheets |

### User Commands (usable in the signup channel)
| Command | Description |
|---------|-------------|
| `/signup` | Sign up for an open race event |
| `/edit-signup` | Edit your existing signup |
| `/cancel-signup` | Cancel your signup |
| `/my-signups` | View your current signups |
| `/view-signups` | View all signups for an event |
| `/list-events` | View all race events |

---

## How It Works

1. An admin creates an event with `/create-event`, specifying classes, cars, timeslots, and an optional deadline
2. Drivers use `/signup` — they pick an event from a dropdown, then fill out a form with their class preferences, car choices, and timeslot availability
3. All signups are stored in the Google Sheet in real time, making it easy for race directors to view and organize
4. The bot sends automatic reminders at 24 hours and 1 hour before a deadline, and auto-closes signups when the deadline passes

---

## Default Timeslots

The bot comes with these default timeslots (used when you don't specify custom ones):
- Slot 1 - Friday Evening
- Slot 2 - Saturday Morning
- Slot 3 - Saturday Afternoon
- Slot 4 - Saturday Evening
- Slot 5 - Sunday Morning
- Slot 6 - Sunday Afternoon

You can customize these per event when creating it, or change the defaults in `config.py`.

---

## Hosting on Railway (Recommended)

1. Push this code to GitHub
2. Go to https://railway.app and sign in with GitHub
3. Click **"New Project"** > **"Deploy from GitHub Repo"**
4. Select this repository
5. Add your environment variables (from `.env`) in the Railway dashboard
6. Upload your `credentials.json` as a file or base64-encode it as an env var
7. Railway will auto-deploy and keep the bot running

---

## Troubleshooting

- **"Application did not respond"**: The bot might be slow on the first Google Sheets call. This is normal — subsequent calls are faster.
- **Slash commands not showing up**: It can take up to an hour for Discord to propagate slash commands globally. For instant testing, you can sync to a specific guild by modifying `bot.py`.
- **Google Sheets errors**: Make sure the service account email has Editor access to the spreadsheet.
