"""
🤖 CRYPTO TRADING BOT
Strategy: EMA Crossover + RSI + ATR Stop Loss
Exchange: Binance Testnet (safe to start)
Runs: 24/7 on 5-minute candles
"""

import ccxt
import pandas as pd
import pandas_ta as ta
import time
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from risk_manager import RiskManager
from logger import setup_logger, log_trade
from notifier import send_email
import traceback
import threading
from flask import Flask

# ── Load API keys from .env ──────────────────────────────────────────────────
load_dotenv()
API_KEY    = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
TESTNET    = os.getenv("TESTNET", "true").lower() == "true"

# ── Bot Configuration ────────────────────────────────────────────────────────
CONFIG = {
    "symbol":        "BTC/USDT",   # Trading pair
    "timeframe":     "5m",         # 5-minute candles
    "ema_fast":      9,            # Fast EMA period
    "ema_slow":      21,           # Slow EMA period
    "rsi_period":    14,           # RSI period
    "rsi_overbought":65,           # RSI sell threshold
    "rsi_oversold":  35,           # RSI buy threshold
    "atr_period":    14,           # ATR for stop loss
    "atr_sl_mult":   1.5,          # Stop loss = 1.5x ATR
    "atr_tp_mult":   3.0,          # Take profit = 3x ATR (2:1 R:R)
    "risk_per_trade":0.02,         # Risk 2% of balance per trade
    "loop_sleep":    60,           # Check every 60 seconds
    "report_interval": 4 * 60 * 60, # 4-hour report (seconds)
}

# ── Setup ────────────────────────────────────────────────────────────────────
logger = setup_logger()

def connect_exchange():
    """Connect to Binance (Testnet or Live)"""
    exchange = ccxt.binance({
        "apiKey":    API_KEY,
        "secret":    API_SECRET,
        "enableRateLimit": True,
        "options":   {
            "defaultType": "spot",
            "adjustForTimeDifference": True
        },
    })
    if TESTNET:
        exchange.set_sandbox_mode(True)
        logger.info("[TESTNET] Connected to BINANCE TESTNET (no real money)")
    else:
        logger.info("[LIVE] Connected to BINANCE LIVE")
    return exchange


def fetch_candles(exchange, symbol, timeframe, limit=100):
    """Fetch OHLCV candle data"""
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def calculate_indicators(df):
    """Add EMA, RSI, ATR indicators to dataframe"""
    df["ema_fast"] = ta.ema(df["close"], length=CONFIG["ema_fast"])
    df["ema_slow"] = ta.ema(df["close"], length=CONFIG["ema_slow"])
    df["rsi"]      = ta.rsi(df["close"], length=CONFIG["rsi_period"])
    df["atr"]      = ta.atr(df["high"], df["low"], df["close"], length=CONFIG["atr_period"])
    return df


def get_signal(df):
    """
    Generate trading signal based on strategy:
    BUY  → Fast EMA crosses above Slow EMA AND RSI < 65 (not overbought)
    SELL → Fast EMA crosses below Slow EMA AND RSI > 35 (not oversold)
    """
    last  = df.iloc[-1]   # current candle
    prev  = df.iloc[-2]   # previous candle

    ema_cross_up   = prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]
    ema_cross_down = prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]
    rsi_ok_buy     = last["rsi"] < CONFIG["rsi_overbought"]
    rsi_ok_sell    = last["rsi"] > CONFIG["rsi_oversold"]

    if ema_cross_up and rsi_ok_buy:
        return "BUY", last
    elif ema_cross_down and rsi_ok_sell:
        return "SELL", last
    return "HOLD", last


def execute_trade(exchange, signal, candle, risk_mgr):
    """Execute buy or sell order with proper risk management"""
    symbol  = CONFIG["symbol"]
    price   = candle["close"]
    atr     = candle["atr"]

    if signal == "BUY":
        stop_loss   = price - (atr * CONFIG["atr_sl_mult"])
        take_profit = price + (atr * CONFIG["atr_tp_mult"])
        qty         = risk_mgr.calculate_position_size(price, stop_loss)

        if qty <= 0:
            logger.warning("Position size too small, skipping trade")
            return

        logger.info(f"BUY  | Price: {price:.2f} | SL: {stop_loss:.2f} | TP: {take_profit:.2f} | Qty: {qty:.6f}")

        order = exchange.create_market_buy_order(symbol, qty)
        log_trade("BUY", price, stop_loss, take_profit, qty, order)
        
        # Send Email Alert
        send_email(
            f"🟢 BUY Order Executed: {symbol}",
            f"Price: {price:.2f}\nStop Loss: {stop_loss:.2f}\nTake Profit: {take_profit:.2f}\nQuantity: {qty:.6f}"
        )

    elif signal == "SELL":
        # Check if we have a position to sell
        balance  = exchange.fetch_balance()
        base_qty = balance["BTC"]["free"] if "BTC" in balance else 0

        if base_qty < 0.0001:
            logger.info("SELL signal but no BTC position held, skipping")
            return

        stop_loss   = price + (atr * CONFIG["atr_sl_mult"])
        take_profit = price - (atr * CONFIG["atr_tp_mult"])

        logger.info(f"SELL | Price: {price:.2f} | Qty: {base_qty:.6f}")
        order = exchange.create_market_sell_order(symbol, base_qty)
        log_trade("SELL", price, stop_loss, take_profit, base_qty, order)
        
        # Send Email Alert
        send_email(
            f"🔴 SELL Order Executed: {symbol}",
            f"Price: {price:.2f}\nQuantity: {base_qty:.6f}"
        )


def get_last_entry_price(exchange):
    """Fetch the last BUY order price from history for P&L tracking"""
    try:
        trades = exchange.fetch_my_trades(CONFIG["symbol"], limit=10)
        # Look for the most recent BUY trade
        for trade in reversed(trades):
            if trade["side"] == "buy":
                return float(trade["price"]), float(trade["amount"])
    except Exception as e:
        logger.error(f"Could not fetch trade history: {e}")
    return None, None

def send_periodic_report(exchange, df):
    """Generate and send summary report with Unrealized P&L"""
    try:
        balance = exchange.fetch_balance()
        total_usdt = balance["USDT"]["total"] if "USDT" in balance else 0
        btc_held   = balance["BTC"]["total"] if "BTC" in balance else 0
        
        last_candle = df.iloc[-1]
        current_price = last_candle["close"]
        
        # Calculate Unrealized P&L
        entry_price, entry_qty = get_last_entry_price(exchange)
        pnl_str = "N/A (No open position tracked)"
        
        if entry_price and btc_held > 0.0001:
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            pnl_usdt = (current_price - entry_price) * btc_held
            pnl_str = f"{pnl_pct:+.2f}% ({pnl_usdt:+.2f} USDT)"

        report_body = (
            f"🕒 4-Hour Bot Report\n"
            f"-------------------\n"
            f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Mode: {'TESTNET' if TESTNET else 'LIVE'}\n\n"
            f"💰 Portfolio Summary:\n"
            f"   Total USDT: {total_usdt:.2f}\n"
            f"   BTC Held  : {btc_held:.6f}\n"
            f"   Current Price: {current_price:.2f}\n"
            f"   Unrealized P&L: {pnl_str}\n\n"
            f"📈 Strategy Context:\n"
            f"   RSI: {last_candle['rsi']:.1f}\n"
            f"   EMA9/21: {last_candle['ema_fast']:.2f} / {last_candle['ema_slow']:.2f}\n\n"
            f"Bot is running normally. Next report in 4 hours."
        )
        send_email(f"📉 Trading Bot Report - {total_usdt:.2f} USDT", report_body)
        logger.info("Periodic report sent via email")
    except Exception as e:
        logger.error(f"Failed to generate report: {e}")

def send_daily_summary(exchange):
    """Send a 24-hour performance summary"""
    try:
        # Fetch trades from the last 24 hours
        since = exchange.milliseconds() - 24 * 60 * 60 * 1000
        trades = exchange.fetch_my_trades(CONFIG["symbol"], since=since)
        
        num_trades = len(trades)
        total_pnl = 0
        # Simple P&L calculation (Sell Price - Buy Price)
        # Note: This is an approximation based on trades in the last 24h
        buys  = [t for t in trades if t["side"] == "buy"]
        sells = [t for t in trades if t["side"] == "sell"]
        
        # Realized P&L for closed pairs
        for s in sells:
            # Match with most recent buy (simplified)
            if buys:
                b = buys.pop()
                total_pnl += (s["price"] - b["price"]) * min(s["amount"], b["amount"])

        balance = exchange.fetch_balance()
        current_bal = balance["USDT"]["total"] if "USDT" in balance else 0
        start_bal = current_bal - total_pnl
        
        pnl_pct = (total_pnl / start_bal * 100) if start_bal > 0 else 0

        summary_body = (
            f"📅 DAILY PERFORMANCE REPORT\n"
            f"---------------------------\n"
            f"Period: Last 24 Hours\n"
            f"Trades Executed: {num_trades}\n\n"
            f"💵 Performance Summary:\n"
            f"   Starting Balance: {start_bal:.2f} USDT\n"
            f"   Ending Balance  : {current_bal:.2f} USDT\n"
            f"   Total Daily P&L : {total_pnl:+.2f} USDT ({pnl_pct:+.2f}%)\n\n"
            f"Next daily summary in 24 hours."
        )
        send_email(f"🏆 Daily Bot Summary: {total_pnl:+.2f} USDT", summary_body)
        logger.info("📩 Daily summary sent via email")
    except Exception as e:
        logger.error(f"Failed to generate daily summary: {e}")

# ── Render Free Tier Health Check ───────────────────────────────────────────
app = Flask(__name__)

@app.route("/")
def health_check():
    return "Bot is alive!", 200

def run_health_check_server():
    # Render provides PORT environment variable
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def run_bot():
    """Main 24/7 bot loop"""
    # Start health check server in background thread for Render
    server_thread = threading.Thread(target=run_health_check_server, daemon=True)
    server_thread.start()
    
    logger.info("=" * 55)
    logger.info("🤖 TRADING BOT STARTED")
    logger.info(f"   Pair      : {CONFIG['symbol']}")
    logger.info(f"   Timeframe : {CONFIG['timeframe']}")
    logger.info(f"   Strategy  : EMA({CONFIG['ema_fast']}/{CONFIG['ema_slow']}) + RSI({CONFIG['rsi_period']})")
    logger.info(f"   Mode      : {'TESTNET' if TESTNET else '⚠️  LIVE'}")
    logger.info("=" * 55)

    exchange = connect_exchange()
    risk_mgr = RiskManager(exchange, CONFIG["risk_per_trade"])
    
    last_report_time = time.time()
    last_daily_time  = time.time()
    
    # Send startup notification
    send_email("Trading Bot Started", f"Bot is now active in {'TESTNET' if TESTNET else 'LIVE'} mode on {CONFIG['symbol']}")

    while True:
        try:
            now = datetime.now().strftime("%H:%M:%S")

            # 1. Fetch data
            df = fetch_candles(exchange, CONFIG["symbol"], CONFIG["timeframe"])

            # 2. Calculate indicators
            df = calculate_indicators(df)

            # 3. Get signal
            signal, candle = get_signal(df)

            # 4. Log current state
            last = df.iloc[-1]
            logger.info(
                f"[{now}] Price: {last['close']:.2f} | "
                f"EMA9: {last['ema_fast']:.2f} | EMA21: {last['ema_slow']:.2f} | "
                f"RSI: {last['rsi']:.1f} | Signal: {signal}"
            )

            # 5. Execute if signal
            if signal != "HOLD":
                execute_trade(exchange, signal, candle, risk_mgr)

            # 6. Periodic Reporting (every 4 hours)
            if time.time() - last_report_time >= CONFIG["report_interval"]:
                send_periodic_report(exchange, df)
                last_report_time = time.time()

            # 7. Daily Summary (every 24 hours)
            if time.time() - last_daily_time >= 24 * 60 * 60:
                send_daily_summary(exchange)
                last_daily_time = time.time()

            # 8. Wait before next check
            time.sleep(CONFIG["loop_sleep"])

        except ccxt.NetworkError as e:
            logger.error(f"Network error: {e} — retrying in 30s")
            time.sleep(30)
        except ccxt.ExchangeError as e:
            logger.error(f"Exchange error: {e} — retrying in 60s")
            time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            time.sleep(30)


if __name__ == "__main__":
    run_bot()
