# trading_logic.py

import os
import asyncio
import logging
import ccxt

# pull your Binance creds from env
API_KEY    = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

# single exchange instance
exchange = ccxt.binance({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    # if you need proxy support:
    # "urls": {"api": {"public": PROXY_URL, "private": PROXY_URL}}
})

async def trading_loop(bot_state):
    """
    Continuously poll each symbol’s price and log it.
    """
    symbols      = bot_state["symbols"]
    interval     = bot_state["poll_interval"]
    last_prices  = bot_state.setdefault("last_prices", {})

    while bot_state["is_running"]:
        for sym in symbols:
            ticker = await asyncio.get_event_loop().run_in_executor(
                None, lambda: exchange.fetch_ticker(sym)
            )
            price = ticker["last"]
            previous = last_prices.get(sym, price)
            logging.info(f"{sym}: price={price:.4f}, last={previous:.4f}")
            last_prices[sym] = price
        await asyncio.sleep(interval)

async def start_trading(bot_state, update=None, context=None):
    """
    Kick off the trading loop in the background.
    """
    if bot_state.get("trading_task") and not bot_state["trading_task"].done():
        # already running
        return

    bot_state["last_status"] = "Trading started"
    bot_state["is_running"] = True
    logging.info("Trading started")

    # launch background task
    bot_state["trading_task"] = asyncio.create_task(trading_loop(bot_state))

async def stop_trading(bot_state):
    """
    Stop trading task cleanly.
    """
    bot_state["is_running"] = False
    bot_state["last_status"] = "Trading stopped"
    logging.info("Trading stopped")
    task = bot_state.get("trading_task")
    if task:
        await task  # wait for loop to finish one last cycle

async def get_status(bot_state):
    """
    Return summary of status & positions.
    """
    status    = bot_state.get("last_status", "Unknown")
    positions = bot_state.get("positions", {})
    return f"Status: {status}\nPositions: {positions}"

def log_tax_event(bot_state, amount, reason):
    """
    Record a tax event in memory.
    """
    entry = {
        "amount": amount,
        "reason": reason,
        "timestamp": asyncio.get_event_loop().time()
    }
    bot_state.setdefault("tax_log", []).append(entry)
    logging.info(f"Tax event logged: {entry}")