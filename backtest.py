"""
📈 BACKTESTER
Test the strategy on historical data BEFORE going live.
Run this first! Never deploy without backtesting.

Usage: python backtest.py
"""

import ccxt
import pandas as pd
import pandas_ta_classic as ta
from datetime import datetime

# ── Config (must match bot.py) ───────────────────────────────────────────────
CONFIG = {
    "symbol":        "BTC/USDT",
    "timeframe":     "5m",
    "ema_fast":      9,
    "ema_slow":      21,
    "rsi_period":    14,
    "rsi_overbought":65,
    "rsi_oversold":  35,
    "atr_period":    14,
    "atr_sl_mult":   1.5,
    "atr_tp_mult":   3.0,
    "initial_balance":100.0,
    "risk_per_trade": 0.02,
    "min_ema_spread": 0.0001,   # 0.01% min spread
    "trailing_sl_pct": 0.005,  # 0.5% trailing stop
}


def fetch_historical(symbol, timeframe, limit=1000):
    """Fetch last N candles from Binance (no API key needed for public data)"""
    print(f"📥 Fetching {limit} candles for {symbol} ({timeframe})...")
    exchange = ccxt.binance({"enableRateLimit": True})
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def add_indicators(df):
    df["ema_fast"] = ta.ema(df["close"], length=CONFIG["ema_fast"])
    df["ema_slow"] = ta.ema(df["close"], length=CONFIG["ema_slow"])
    df["rsi"]      = ta.rsi(df["close"], length=CONFIG["rsi_period"])
    df["atr"]      = ta.atr(df["high"], df["low"], df["close"], length=CONFIG["atr_period"])
    return df.dropna()


def run_backtest(df):
    balance    = CONFIG["initial_balance"]
    position   = None   # {"entry": price, "qty": qty, "sl": sl, "tp": tp}
    trades     = []
    peak_bal   = balance

    for i in range(1, len(df)):
        row  = df.iloc[i]
        prev = df.iloc[i - 1]

        # ── Check active position (Stop Loss / Take Profit / Trailing Stop) ──
        if position:
            # Update Highest Price for Trailing Stop
            position["highest_price"] = max(position["highest_price"], row["high"])
            
            # Calculate Trailing Stop Level
            trailing_sl = position["highest_price"] * (1 - CONFIG["trailing_sl_pct"])
            
            if row["low"] <= position["sl"]:
                # Fixed Stop loss hit
                pnl     = (position["sl"] - position["entry"]) * position["qty"]
                balance += position["qty"] * position["sl"]
                trades.append({"type": "SL", "pnl": pnl, "balance": balance})
                position = None
                continue
            
            elif row["low"] <= trailing_sl:
                # Trailing Stop hit
                pnl     = (trailing_sl - position["entry"]) * position["qty"]
                balance += position["qty"] * trailing_sl
                trades.append({"type": "TSL", "pnl": pnl, "balance": balance})
                position = None
                continue

            elif row["high"] >= position["tp"]:
                # Take profit hit
                pnl     = (position["tp"] - position["entry"]) * position["qty"]
                balance += position["qty"] * position["tp"]
                trades.append({"type": "TP", "pnl": pnl, "balance": balance})
                position = None
                continue

        # ── Generate Signals ─────────────────────────────────────────────────
        ema9, ema21 = row["ema_fast"], row["ema_slow"]
        prev_ema9, prev_ema21 = prev["ema_fast"], prev["ema_slow"]
        
        ema_uptrend = ema9 > ema21
        ema_cross_up = prev_ema9 <= prev_ema21 and ema9 > ema21
        
        # Spread calculation
        spread = (ema9 - ema21) / ema21
        prev_spread = (prev_ema9 - prev_ema21) / prev_ema21
        momentum_ok = spread > prev_spread and spread > CONFIG["min_ema_spread"]
        
        rsi_ok = row["rsi"] < CONFIG["rsi_overbought"]
        
        # Pullback check (Price low touches or dips below EMA9 while in uptrend)
        pullback_ok = row["low"] <= ema9 and row["close"] > ema9
        
        signal = False
        if rsi_ok and momentum_ok and not position:
            if ema_cross_up:
                signal = "Crossover"
            elif ema_uptrend and pullback_ok:
                signal = "Pullback"
            
            if signal:
                print(f"DEBUG: Found {signal} signal at {row['timestamp']} | RSI: {row['rsi']:.1f} | Spread: {spread*100:.3f}%")

        if signal:
            price = row["close"]
            sl    = price - (row["atr"] * CONFIG["atr_sl_mult"])
            tp    = price + (row["atr"] * CONFIG["atr_tp_mult"])

            risk_amount  = balance * CONFIG["risk_per_trade"]
            risk_per_unit = price - sl
            qty = risk_amount / risk_per_unit if risk_per_unit > 0 else 0

            # Safety cap: Never spend more than 95% of balance
            max_qty = (balance * 0.95) / price
            qty = min(qty, max_qty)

            if qty > 0.00001:  # Min trade size check
                balance  -= price * qty
                peak_bal  = max(peak_bal, balance)
                position  = {
                    "entry": price, 
                    "qty": qty, 
                    "sl": sl, 
                    "tp": tp, 
                    "highest_price": price, 
                    "reason": signal
                }
                print(f"✅ EXECUTE {signal} | Price: {price:.2f} | Qty: {qty:.6f}")

    # ── Results ──────────────────────────────────────────────────────────────
    final_balance = CONFIG["initial_balance"] if not trades else trades[-1]["balance"]
    total_pnl     = final_balance - CONFIG["initial_balance"]
    wins          = [t for t in trades if t["pnl"] > 0]
    losses        = [t for t in trades if t["pnl"] <= 0]
    win_rate      = len(wins) / len(trades) * 100 if trades else 0

    print("\n" + "=" * 50)
    print("📊 BACKTEST RESULTS")
    print("=" * 50)
    print(f"  Period          : {df.iloc[0]['timestamp']} → {df.iloc[-1]['timestamp']}")
    print(f"  Initial Balance : ${CONFIG['initial_balance']:.2f}")
    print(f"  Final Balance   : ${final_balance:.2f}")
    print(f"  Total P&L       : ${total_pnl:.2f} ({total_pnl/CONFIG['initial_balance']*100:.1f}%)")
    print(f"  Total Trades    : {len(trades)}")
    print(f"  Win Rate        : {win_rate:.1f}%")
    print(f"  Wins / Losses   : {len(wins)} / {len(losses)}")
    if wins:
        print(f"  Avg Win         : ${sum(t['pnl'] for t in wins)/len(wins):.2f}")
    if losses:
        print(f"  Avg Loss        : ${sum(t['pnl'] for t in losses)/len(losses):.2f}")
    print("=" * 50)

    if total_pnl > 0 and win_rate > 45:
        print("✅ Strategy looks PROFITABLE — safe to paper trade!")
    else:
        print("⚠️  Strategy needs tuning before going live.")

    return trades


if __name__ == "__main__":
    df = fetch_historical(CONFIG["symbol"], CONFIG["timeframe"], limit=2000)
    df = add_indicators(df)
    run_backtest(df)
