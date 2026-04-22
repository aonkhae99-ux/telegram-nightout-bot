# Staff Night-Out Tracker Bot

A Telegram bot that tracks staff night-out requests in a group chat with a
monthly limit (default: 4 per person). After the limit is reached, the bot
warns the user and refuses further requests until the next calendar month.

## Setup

1. Talk to [@BotFather](https://t.me/BotFather) on Telegram and create a new
   bot. Copy the token it gives you.

2. In `@BotFather`, run `/setprivacy` for your bot and set it to **Disable**
   if you want the bot to read all messages (not required for command-only
   usage, but recommended).

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Configure the bot:

   ```bash
   cp .env.example .env
   # then edit .env and paste your BOT_TOKEN
   ```

5. Run it:

   ```bash
   python bot.py
   ```

6. Add the bot to your staff group. To allow `/resetmonth` to work properly,
   promote the bot to an admin (or at least allow it to read group members).

## Commands

| Command               | Who        | What it does                                            |
| --------------------- | ---------- | ------------------------------------------------------- |
| `/nightout`           | anyone     | Logs one night-out request for the sender               |
| `/mycount`            | anyone     | Shows how many the sender has used this month           |
| `/stats`              | anyone     | Shows everyone's counts for the current month           |
| `/resetmonth @user`   | admin only | Clears that user's count for the current month          |
| `/start` or `/help`   | anyone     | Shows the help message                                  |

`/resetmonth` also works by **replying** to a user's message with the command.

## Configuration

Environment variables (set in `.env`):

- `BOT_TOKEN` — your Telegram bot token (required)
- `MONTHLY_LIMIT` — max requests per user per month (default: `4`)
- `DB_PATH` — path to the SQLite file (default: `nightout.db`)

## How counting works

- Counts reset automatically on the 1st of each calendar month (UTC).
- Each chat is tracked independently — the same user in two different groups
  has separate counts.
- All data is stored locally in a SQLite file (`nightout.db` by default).
