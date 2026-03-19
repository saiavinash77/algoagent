
import bot
import os
from dotenv import load_dotenv

load_dotenv()

def verify_reports():
    print("🚀 Starting Report Verification...")
    exchange = bot.connect_exchange()
    
    # 1. Fetch some data to populate df
    print("📥 Fetching data for report context...")
    df = bot.fetch_candles(exchange, bot.CONFIG["symbol"], bot.CONFIG["timeframe"], limit=50)
    df = bot.calculate_indicators(df)
    
    # 2. Test 4-Hour Report
    print("📧 Sending 4-Hour Report Test...")
    bot.send_periodic_report(exchange, df)
    
    # 3. Test Daily Summary
    print("📧 Sending Daily Summary Test...")
    bot.send_daily_summary(exchange)
    
    print("✅ Verification complete. Check your email!")

if __name__ == "__main__":
    verify_reports()
