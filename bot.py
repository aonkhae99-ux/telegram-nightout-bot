"""
Staff Night-Out Tracker Telegram Bot

Tracks staff night-out requests in a Telegram group with a monthly limit
of 4 per person. Warns the user when the limit is reached and blocks
further requests until the next calendar month.
"""

import logging
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
MONTHLY_LIMIT = int(os.environ.get("MONTHLY_LIMIT", "4"))
DB_PATH = Path(os.environ.get("DB_PATH", "nightout.db"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def init_db() -> None:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                username    TEXT,
                full_name   TEXT,
                year        INTEGER NOT NULL,
                month       INTEGER NOT NULL,
                created_at  TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_requests_lookup "
            "ON requests (chat_id, user_id, year, month)"
        )
        conn.commit()


def current_year_month() -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    return now.year, now.month


def count_for_month(chat_id: int, user_id: int, year: int, month: int) -> int:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute(
            "SELECT COUNT(*) FROM requests "
            "WHERE chat_id = ? AND user_id = ? AND year = ? AND month = ?",
            (chat_id, user_id, year, month),
        )
        (count,) = cur.fetchone()
        return int(count)


def insert_request(
    chat_id: int,
    user_id: int,
    username: str | None,
    full_name: str,
    year: int,
    month: int,
) -> None:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            "INSERT INTO requests "
            "(chat_id, user_id, username, full_name, year, month, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                chat_id,
                user_id,
                username,
                full_name,
                year,
                month,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def delete_month_for_user(
    chat_id: int, user_id: int, year: int, month: int
) -> int:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute(
            "DELETE FROM requests "
            "WHERE chat_id = ? AND user_id = ? AND year = ? AND month = ?",
            (chat_id, user_id, year, month),
        )
        conn.commit()
        return cur.rowcount


async def is_admin(update: Update, user_id: int) -> bool:
    chat = update.effective_chat
    if chat is None:
        return False
    if chat.type == "private":
        return True
    try:
        member = await chat.get_member(user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def display_name(user) -> str:
    if user.username:
        return f"@{user.username}"
    return user.full_name or str(user.id)


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! I track staff night-out requests.\n\n"
        f"Each person can request up to {MONTHLY_LIMIT} per month.\n\n"
        "Commands:\n"
        "/nightout - log a night-out request\n"
        "/mycount - see how many you've used this month\n"
        "/stats - see this month's stats for the group\n"
        "/resetmonth @user - admin only: reset a user's count\n"
    )


async def cmd_nightout(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None or update.message is None:
        return

    year, month = current_year_month()
    used = count_for_month(chat.id, user.id, year, month)
    name = display_name(user)

    if used >= MONTHLY_LIMIT:
        await update.message.reply_text(
            f"{name}, you've already hit the {MONTHLY_LIMIT}-per-month limit. "
            f"No more night-outs this month - try again next month."
        )
        return

    insert_request(chat.id, user.id, user.username, user.full_name or "", year, month)
    new_used = used + 1
    remaining = MONTHLY_LIMIT - new_used

    if new_used >= MONTHLY_LIMIT:
        await update.message.reply_text(
            f"Logged. {name}, that's #{new_used} this month - you've now reached the "
            f"limit of {MONTHLY_LIMIT}. No more requests until next month."
        )
    else:
        await update.message.reply_text(
            f"Logged. {name}, that's #{new_used} this month. "
            f"{remaining} left."
        )


async def cmd_mycount(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None or update.message is None:
        return

    year, month = current_year_month()
    used = count_for_month(chat.id, user.id, year, month)
    remaining = max(MONTHLY_LIMIT - used, 0)
    name = display_name(user)

    await update.message.reply_text(
        f"{name}: {used}/{MONTHLY_LIMIT} used this month. {remaining} remaining."
    )


async def cmd_stats(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or update.message is None:
        return

    year, month = current_year_month()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute(
            """
            SELECT username, full_name, COUNT(*) as c
            FROM requests
            WHERE chat_id = ? AND year = ? AND month = ?
            GROUP BY user_id
            ORDER BY c DESC, full_name ASC
            """,
            (chat.id, year, month),
        )
        rows = cur.fetchall()

    if not rows:
        await update.message.reply_text("No night-outs logged yet this month.")
        return

    month_label = datetime(year, month, 1).strftime("%B %Y")
    lines = [f"*Night-outs for {month_label}:*"]
    for username, full_name, count in rows:
        name = f"@{username}" if username else (full_name or "unknown")
        flag = " (limit reached)" if count >= MONTHLY_LIMIT else ""
        lines.append(f"- {name}: {count}/{MONTHLY_LIMIT}{flag}")

    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN
    )


async def cmd_resetmonth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None or update.message is None:
        return

    if not await is_admin(update, user.id):
        await update.message.reply_text("Only group admins can reset counts.")
        return

    target_user_id: int | None = None
    target_label: str | None = None

    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        t = update.message.reply_to_message.from_user
        target_user_id = t.id
        target_label = display_name(t)
    elif context.args:
        arg = context.args[0]
        if arg.startswith("@"):
            uname = arg[1:].lower()
            with closing(sqlite3.connect(DB_PATH)) as conn:
                cur = conn.execute(
                    "SELECT user_id, username FROM requests "
                    "WHERE chat_id = ? AND LOWER(username) = ? "
                    "ORDER BY id DESC LIMIT 1",
                    (chat.id, uname),
                )
                row = cur.fetchone()
            if row:
                target_user_id = int(row[0])
                target_label = f"@{row[1]}"

    if target_user_id is None:
        await update.message.reply_text(
            "Usage: reply to the user's message with /resetmonth, "
            "or use /resetmonth @username (the user must have logged at least one "
            "request before)."
        )
        return

    year, month = current_year_month()
    removed = delete_month_for_user(chat.id, target_user_id, year, month)
    await update.message.reply_text(
        f"Reset {target_label}: cleared {removed} request(s) for this month."
    )


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN is not set. Copy .env.example to .env and add your token."
        )

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("nightout", cmd_nightout))
    app.add_handler(CommandHandler("mycount", cmd_mycount))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("resetmonth", cmd_resetmonth))

    logger.info("Bot starting (monthly limit = %s)...", MONTHLY_LIMIT)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
