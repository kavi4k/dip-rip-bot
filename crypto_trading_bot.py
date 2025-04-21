import os
import time
import logging
import traceback
import signal
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import ccxt

load_dotenv()

# Environment Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Logging
logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Global bot state
RUNNING = True
STATUS_MESSAGE = "Bot is running and monitoring prices."

# Exchange Setup
exchange = ccxt.binance({
    'apiKey': os.getenv("API_KEY"),
    'secret': os.getenv("API_SECRET"),
    'enableRateLimit': True,
    'options': { 'defaultType': 'spot' },
})

# Telegram Commands
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"✅ {STATUS_MESSAGE if RUNNING else 'Bot is paused.'}")

async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global RUNNING
    RUNNING = False
    await update.message.reply_text("⏸️ Bot paused.")

async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global RUNNING
    RUNNING = True
    await update.message.reply_text("▶️ Bot resumed.")

# Price Monitoring Loop
def monitor_prices():
    symbols = os.getenv("SYMBOLS", "BTC/USDT").split(',')
    while True:
        try:
            if RUNNING:
                for symbol in symbols:
                    ticker = exchange.fetch_ticker(symbol)
                    price = ticker['last']
                    logger.info(f"{symbol}: {price}")
            time.sleep(10)
        except Exception as e:
            error_msg = f"❗ Bot crashed: {str(e)}"
            logger.error(traceback.format_exc())
            send_telegram_alert(error_msg)
            time.sleep(30)  # wait before retrying

# Telegram Crash Alert
import requests

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, data=data)
    except Exception as e:
        logger.error("Failed to send alert: " + str(e))

# Signal Handling
def shutdown_handler(signum, frame):
    logger.info("Received shutdown signal")
    send_telegram_alert("⚠️ Bot was terminated (manually or by system).")
    exit(0)

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# Telegram Bot Setup
async def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("pause", pause))
    application.add_handler(CommandHandler("resume", resume))

    await application.start()
    send_telegram_alert("✅ Dip-Rip bot started and Telegram interface online.")
    monitor_prices()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())