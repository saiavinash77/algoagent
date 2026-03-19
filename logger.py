"""
📋 LOGGER
Logs every trade and bot event to console + trades.csv file
"""

import logging
import csv
import os
from datetime import datetime


def setup_logger():
    """Setup clean console + file logging"""
    logger = logging.getLogger("TradingBot")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger  # Already set up

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # File handler
    os.makedirs("logs", exist_ok=True)
    file_handler = logging.FileHandler("logs/bot.log")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    logger.addHandler(console)
    logger.addHandler(file_handler)
    return logger


def log_trade(side, price, stop_loss, take_profit, quantity, order, reason="N/A"):
    """Log every trade to trades.csv for later analysis"""
    os.makedirs("logs", exist_ok=True)
    filepath = "logs/trades.csv"
    file_exists = os.path.isfile(filepath)

    with open(filepath, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "timestamp", "side", "price", "stop_loss",
                "take_profit", "quantity", "order_id", "status", "reason"
            ])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            side,
            round(price, 2),
            round(stop_loss, 2),
            round(take_profit, 2),
            quantity,
            order.get("id", "N/A"),
            order.get("status", "N/A"),
            reason
        ])
