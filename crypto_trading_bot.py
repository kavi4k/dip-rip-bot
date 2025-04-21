# crypto_trading_bot.py
# =====================
"""
Crypto Trading Bot controlled via Telegram

Features:
- Buy-the-dip / sell-the-rip on multiple symbols
- Safe retry logic for network calls
- Resilient to IP-restricted Binance keys
- Never-die trading loop with comprehensive try/except

Commands:
/startTrading    — start trading loop
/stopTrading     — pause trading
/backtest [SYM]  — simple backtest on 1m data
/plot            — send P&L chart

Setup:
1. Create a `.env` with your keys and settings:
   ```env
   API_KEY=...
   API_SECRET=...
   TELEGRAM_TOKEN=...
   TELEGRAM_CHAT_ID=...
   SYMBOLS=BTC/USDT,ADA/USDT,...
   INVESTMENT_AMOUNT_USD=10
   DIP_THRESHOLD_PERCENT=1.0
   RIP_THRESHOLD_PERCENT=2.0
   POLL_INTERVAL_SECONDS=60
   MIN_HOLD_TIME_SECONDS=300
   DAILY_DRAWDOWN_LIMIT=0.05
   # PROXY_URL not required if your machine IP is whitelisted
   ```
2. Install dependencies:
   ```bash
   pip install ccxt pandas python-telegram-bot python-dotenv matplotlib requests
   ```
3. Run:
   ```bash
   source venv/bin/activate
   python crypto_trading_bot.py
   ```
"""
import os, time, logging, csv, threading
from datetime import datetime, date, timedelta

import requests
import ccxt
import pandas as pd
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Load .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
PROXY_URL = os.getenv("PROXY_URL")  # optional

# Apply proxy if provided
if PROXY_URL:
    os.environ['HTTP_PROXY'] = PROXY_URL
    os.environ['HTTPS_PROXY'] = PROXY_URL

# Telegram URL
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

# Trading settings
SYMBOLS = os.getenv("SYMBOLS", "BTC/USDT").split(",")
INVESTMENT_AMOUNT_USD = float(os.getenv("INVESTMENT_AMOUNT_USD", "10"))
BASE_DIP = float(os.getenv("DIP_THRESHOLD_PERCENT", "1.0")) / 100
BASE_RIP = float(os.getenv("RIP_THRESHOLD_PERCENT", "2.0")) / 100
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
MIN_HOLD = int(os.getenv("MIN_HOLD_TIME_SECONDS", "300"))
DAILY_DRAWDOWN_LIMIT = float(os.getenv("DAILY_DRAWDOWN_LIMIT", "0.05"))

# State
running_event = threading.Event()
positions = {}
last_summary_date = date.today()
starting_balance = 0.0

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# Instantiate Binance (spot only)
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
        'fetchCurrencies': False,
    },
})
# disable margin endpoints so IP-restricted keys work
exchange.has['margin'] = False

# Ensure trade log exists
LOG_FILE = 'trades.csv'
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, 'w', newline='') as f:
        csv.writer(f).writerow(['timestamp','symbol','side','price','amount','fee','usdt_delta'])

# Retry helper
def retry_call(func, *args, retries=3, delay=2):
    for i in range(retries - 1):
        try:
            return func(*args)
        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.RequestException) as e:
            logging.warning(f"Network error ({e}), retry {i+1}/{retries}...")
            time.sleep(delay)
    return func(*args)

# Telegram sender
def send_telegram(msg: str):
    try:
        requests.post(TELEGRAM_URL, data={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': msg,
            'parse_mode': 'Markdown'
        }, timeout=10)
    except Exception as e:
        logging.error(f"Telegram error: {e}")

# Wrapped exchange calls
def fetch_balance_usdt() -> float:
    bal = retry_call(exchange.fetch_balance)
    return float(bal.get('USDT', {}).get('total', 0.0))

def safe_fetch_ticker(symbol: str) -> float:
    ticker = retry_call(exchange.fetch_ticker, symbol)
    return float(ticker.get('last', 0.0))

def safe_create_order(symbol, type_, side, amount, price):
    return retry_call(exchange.create_order, symbol, type_, side, amount, price)

# Initialize positions
def init_positions():
    global starting_balance
    starting_balance = fetch_balance_usdt()
    for sym in SYMBOLS:
        price = safe_fetch_ticker(sym)
        positions[sym] = { 'in': False, 'last_price': price, 'buy_time': None, 'buy_price': None }
    send_telegram(f"🤖 Ready. Balance: {starting_balance:.2f} USDT. Use /startTrading to begin.")

# Daily P&L summary
def daily_summary():
    global last_summary_date, starting_balance
    today = date.today()
    if today > last_summary_date:
        df = pd.read_csv(LOG_FILE, parse_dates=['timestamp'])
        start = datetime.combine(last_summary_date, datetime.min.time())
        end   = start + timedelta(days=1)
        df_day = df[(df['timestamp'] >= start) & (df['timestamp'] < end)]
        pnl    = df_day['usdt_delta'].sum()
        trades = len(df_day)
        send_telegram(f"📊 {last_summary_date}: Trades={trades}, P&L={pnl:.2f} USDT")
        starting_balance = fetch_balance_usdt()
        last_summary_date = today

# Trading loop (never dies)
def trading_loop():
    while True:
        if not running_event.is_set():
            time.sleep(1)
            continue
        try:
            daily_summary()
            try:
                bal = fetch_balance_usdt()
            except Exception as e:
                logging.error(f"Balance fetch failed: {e}")
                time.sleep(POLL_INTERVAL)
                continue
            if bal < starting_balance * (1 - DAILY_DRAWDOWN_LIMIT):
                send_telegram("⚠️ Daily drawdown hit. Pausing trades.")
                running_event.clear()
                continue
            for sym, st in positions.items():
                try:
                    price = safe_fetch_ticker(sym)
                    logging.info(f"{sym}: price={price:.4f}, last={st['last_price']:.4f}")
                    if not st['in'] and price <= st['last_price'] * (1 - BASE_DIP):
                        amt = round(INVESTMENT_AMOUNT_USD / price, 8)
                        order = safe_create_order(sym, 'limit', 'buy', amt, price)
                        st['in'] = True
                        st['buy_time'] = datetime.now()
                        st['buy_price'] = price
                        fee = order.get('fee', {}).get('cost', 0)
                        delta = -(price * amt + fee)
                        csv.writer(open(LOG_FILE,'a',newline='')).writerow([datetime.now().isoformat(), sym, 'buy', price, amt, fee, delta])
                        send_telegram(f"✅ Bought {sym} @ {price:.4f}")
                    elif st['in'] and (datetime.now()-st['buy_time']).seconds>=MIN_HOLD and price>=st['buy_price']*(1+BASE_RIP):
                        amt = retry_call(exchange.fetch_balance)[sym.split('/')[0]]['free']
                        order = safe_create_order(sym, 'limit', 'sell', amt, price)
                        st['in'] = False
                        st['last_price'] = price
                        fee = order.get('fee', {}).get('cost', 0)
                        delta = price * amt - fee
                        csv.writer(open(LOG_FILE,'a',newline='')).writerow([datetime.now().isoformat(), sym, 'sell', price, amt, fee, delta])
                        send_telegram(f"💰 Sold {sym} @ {price:.4f}")
                    if not st['in']:
                        st['last_price'] = price
                except Exception as e:
                    logging.error(f"Error in {sym}: {e}")
                    send_telegram(f"⚠️ Error {sym}: {e}")
        except Exception as e:
            logging.error(f"Trading loop fatal: {e}")
        time.sleep(POLL_INTERVAL)

# Telegram handlers
async def start_trading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if running_event.is_set():
        await update.message.reply_text("🔄 Trading already running.")
    else:
        running_event.set()
        await update.message.reply_text("🚀 Trading started.")

async def stop_trading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not running_event.is_set():
        await update.message.reply_text("⏸️ Trading already paused.")
    else:
        running_event.clear()
        await update.message.reply_text("🛑 Trading paused.")

async def backtest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sym = context.args[0].upper() if context.args else SYMBOLS[0]
    df = pd.read_csv(f"{sym.replace('/','')}-1m.csv")
    inpos=False;bp=0;trips=0
    for p in df['close']:
        if not inpos and p<=p*(1-BASE_DIP): inpos=True;bp=p
        elif inpos and p>=bp*(1+BASE_RIP): trips+=1; inpos=False
    await update.message.reply_text(f"{sym}: {trips} round trips.")

async def plot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df=pd.read_csv(LOG_FILE,parse_dates=['timestamp'])
    df['cum']=df['usdt_delta'].cumsum()
    plt.figure(); df.groupby(df['timestamp'].dt.date)['cum'].last().plot(marker='o')
    plt.tight_layout(); fn='pnl.png'; plt.savefig(fn)
    await update.message.reply_photo(open(fn,'rb'))

# Entrypoint
if __name__=='__main__':
    init_positions()
    threading.Thread(target=trading_loop, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('startTrading', start_trading))
    app.add_handler(CommandHandler('stopTrading', stop_trading))
    app.add_handler(CommandHandler('backtest', backtest_cmd))
    app.add_handler(CommandHandler('plot', plot_cmd))
    app.run_polling()
