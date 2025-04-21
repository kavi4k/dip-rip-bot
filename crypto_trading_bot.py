import asyncio
import logging
import os
from dotenv import load_dotenv
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)
from trading_logic import start_trading, stop_trading, get_status, log_tax_event, update_anchor_price

# Load environment variables
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ANCHOR_REFRESH_INTERVAL = 4 * 60 * 60  # 4 hours in seconds

# Logging setup
logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Shared bot state
bot_state = {
    "is_running": False,
    "last_status": "Idle",
    "positions": {},
    "tax_log": [],
    "anchor_prices": {}
}

# Telegram Command Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_state["is_running"] = True
    await update.message.reply_text("✅ Trading bot started.")
    await start_trading(bot_state, update, context)

async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_state["is_running"] = False
    await update.message.reply_text("⏸ Trading bot paused.")
    await stop_trading(bot_state)

async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not bot_state["is_running"]:
        bot_state["is_running"] = True
        await update.message.reply_text("▶️ Trading bot resumed.")
        await start_trading(bot_state, update, context)
    else:
        await update.message.reply_text("Bot is already running.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = await get_status(bot_state)
    await update.message.reply_text(f"📊 {status}")

async def tax_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("⚠️ Usage: /tax <amount> <reason>")
        return
    amount = args[0]
    reason = " ".join(args[1:])
    log_tax_event(bot_state, amount, reason)
    await update.message.reply_text(f"🧾 Logged tax event: ${amount} - {reason}")

async def send_telegram_message(message: str):
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        logger.error(f"❌ Failed to send Telegram message: {e}")

# Main function
async def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("pause", pause_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("tax", tax_command))

    # Periodic anchor price update
    application.job_queue.run_repeating(
        lambda ctx: asyncio.create_task(update_anchor_price(bot_state)),
        interval=ANCHOR_REFRESH_INTERVAL,
        first=0,
    )

    try:
        logger.info("Application started")
        await application.run_polling()
    except Exception as e:
        logger.exception("Unhandled error in main(): %s", str(e))
        await send_telegram_message(f"🚨 Bot crashed with error:\n{e}")

if __name__ == '__main__':
    asyncio.run(main())