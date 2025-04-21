import asyncio
import logging
import os
import signal
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, CallbackContext
)
from trading_logic import start_trading, stop_trading, get_status, log_tax_event

# Load environment variables
load_dotenv()

# Telegram settings
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Setup logging
logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot state
bot_state = {
    "is_running": False,
    "last_status": "Idle",
    "positions": {},
    "tax_log": []
}

# Telegram commands
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
    await update.message.reply_text(f"📊 Status: {bot_state['last_status']}\nPositions: {bot_state['positions']}")

async def tax_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("⚠️ Usage: /tax <amount> <reason>")
        return
    amount = args[0]
    reason = " ".join(args[1:])
    log_tax_event(bot_state, amount, reason)
    await update.message.reply_text(f"🧾 Logged tax event: ${amount} - {reason}")

async def send_telegram_message(message):
    from telegram import Bot
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

async def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("pause", pause_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("tax", tax_command))

    try:
        await application.initialize()
        await application.run_polling()
    except Exception as e:
        logger.exception("Unhandled error in main(): %s", str(e))
        await send_telegram_message(f"🚨 Bot crashed with error:\n{e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception("Fatal crash: %s", str(e))
        asyncio.run(send_telegram_message(f"💥 Fatal crash: {e}"))