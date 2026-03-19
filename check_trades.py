
import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

def check_trades():
    exchange = ccxt.binance({
        "apiKey": os.getenv("BINANCE_API_KEY"),
        "secret": os.getenv("BINANCE_API_SECRET"),
        "options": {"adjustForTimeDifference": True},
    })
    exchange.set_sandbox_mode(True)
    
    try:
        trades = exchange.fetch_my_trades("BTC/USDT", limit=5)
        print(f"Fetched {len(trades)} trades.")
        for t in trades:
            print(f"ID: {t['id']} | Side: {t['side']} | Price: {t['price']} | Qty: {t['amount']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_trades()
