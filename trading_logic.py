import asyncio
import logging
import ccxt
import os

exchange = ccxt.binance({
    'apiKey': os.getenv("API_KEY"),
    'secret': os.getenv("API_SECRET"),
    'enableRateLimit': True
})

SYMBOLS = os.getenv("SYMBOLS").split(",")
INVESTMENT_AMOUNT = float(os.getenv("INVESTMENT_AMOUNT_USD"))
DIP_THRESHOLD = float(os.getenv("DIP_THRESHOLD_PERCENT")) / 100
RIP_THRESHOLD = float(os.getenv("RIP_THRESHOLD_PERCENT")) / 100

async def fetch_prices():
    prices = {}
    for symbol in SYMBOLS:
        market = exchange.market(symbol)
        ticker = exchange.fetch_ticker(symbol)
        prices[symbol] = ticker['last']
    return prices

async def update_anchor_price(bot_state):
    prices = await fetch_prices()
    bot_state['anchor_price'] = prices
    logging.info(f"🔁 Anchor prices updated: {prices}")

async def start_trading(bot_state, update=None, context=None):
    bot_state['last_status'] = 'Trading started'
    logging.info("Trading started")
    asyncio.create_task(trading_loop(bot_state))

async def stop_trading(bot_state):
    bot_state['last_status'] = 'Trading stopped'
    logging.info("Trading stopped")

async def get_status(bot_state):
    return f"Status: {bot_state.get('last_status')}\nPositions: {bot_state.get('positions')}\nAnchor: {bot_state.get('anchor_price')}"

def log_tax_event(bot_state, amount, reason):
    entry = {'amount': amount, 'reason': reason, 'timestamp': asyncio.get_event_loop().time()}
    bot_state.setdefault('tax_log', []).append(entry)
    logging.info(f"📜 Tax logged: {entry}")

async def trading_loop(bot_state):
    while bot_state['is_running']:
        prices = await fetch_prices()
        for symbol in SYMBOLS:
            current = prices[symbol]
            anchor = bot_state['anchor_price'].get(symbol)
            if anchor:
                change = (current - anchor) / anchor
                if change <= -DIP_THRESHOLD:
                    logging.info(f"💰 Buying {symbol} at {current} (dip of {change:.2%})")
                    bot_state['positions'][symbol] = current
                elif change >= RIP_THRESHOLD and symbol in bot_state['positions']:
                    entry_price = bot_state['positions'].pop(symbol)
                    profit = current - entry_price
                    logging.info(f"💵 Sold {symbol} at {current}, profit: {profit:.2f}")
        await asyncio.sleep(int(os.getenv("POLL_INTERVAL_SECONDS")))