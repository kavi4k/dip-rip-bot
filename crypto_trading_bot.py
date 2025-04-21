# crypto_trading_bot.py

import os
import asyncio
import logging
from dotenv import load_dotenv
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)
from trading_logic import (
    start_trading,
    stop_trading,
    get_status,
    log_tax_event
)

# ── load config ─────────────────────────────────
load_dotenv()
TELEGRAM_TOKEN       = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID     = os.getenv("TELEGRAM_CHAT_ID")
SYMBOLS              = os.getenv("SYMBOLS", "").split(",")
POLL_INTERVAL        = int(os.getenv("POLL_INTERVAL_SECONDS", 60))

# ── logging ────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── shared state ───────────────────────────────
bot_state = {
    "is_running": False,
    "last_status": "Idle",
    "positions": {},
    "tax_log": [],
    "symbols": SYMBOLS,
    "poll_interval": POLL_INTERVAL,
}

# ── telegram command handlers ──────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Trading bot started.")
    await start_trading(bot_state, update, context)

async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏸ Trading bot paused.")
    await stop_trading(bot_state)

async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not bot_state["is_running"]:
        await update.message.reply_text("▶️ Trading bot resumed.")
        await start_trading(bot_state, update, context)
    else:
        await update.message.reply_text("Bot is already running.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    summary = await get_status(bot_state)
    await update.message.reply_text(f"📊 {summary}")

async def tax_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        return await update.message.reply_text("⚠️ Usage: /tax <amount> <reason>")
    amount, *reason = args
    reason = " ".join(reason)
    log_tax_event(bot_state, amount, reason)
    await update.message.reply_text(f"🧾 Logged tax event: ${amount} – {reason}")

async def shutdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cleanly stop trading + polling and then exit the process.
    """
    await update.message.reply_text("🛑 Shutting down bot…")
    # first stop your trading loop
    await stop_trading(bot_state)
    # then stop the Telegram application’s polling
    await context.application.stop()  # this will make run_polling() return

# helper for crash alerts
async def send_telegram_message(message: str):
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

# ── application setup & run ───────────────────
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("pause", pause_command))
    app.add_handler(CommandHandler("resume", resume_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("tax", tax_command))
    app.add_handler(CommandHandler("shutdown", shutdown_command))

    try:
        app.run_polling()
    except Exception as e:
        logger.exception("Fatal error in bot: %s", e)
        # fire‐and‐forget the crash alert
        asyncio.run(send_telegram_message(f"🚨 Bot crashed:\n{e}"))

if __name__ == "__main__":
    main()