"""
💰 RISK MANAGER
Handles position sizing and balance checks.
Rule: Never risk more than X% of your balance on a single trade.
"""

import logging

logger = logging.getLogger("TradingBot")


class RiskManager:
    def __init__(self, exchange, risk_pct=0.02):
        """
        exchange  : ccxt exchange instance
        risk_pct  : fraction of balance to risk per trade (0.02 = 2%)
        """
        self.exchange = exchange
        self.risk_pct = risk_pct

    def get_usdt_balance(self):
        """Get available USDT balance"""
        try:
            balance = self.exchange.fetch_balance()
            usdt = balance.get("USDT", {}).get("free", 0)
            logger.info(f"💵 Available USDT balance: {usdt:.2f}")
            return float(usdt)
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            return 0.0

    def calculate_position_size(self, entry_price, stop_loss_price):
        """
        Calculate how many BTC to buy based on risk.

        Formula:
            risk_amount  = balance * risk_pct
            risk_per_unit = entry - stop_loss
            quantity     = risk_amount / risk_per_unit
        """
        balance      = self.get_usdt_balance()
        risk_amount  = balance * self.risk_pct
        risk_per_unit = abs(entry_price - stop_loss_price)

        if risk_per_unit == 0:
            logger.warning("Risk per unit is 0, cannot size position")
            return 0

        quantity = risk_amount / risk_per_unit

        # Make sure we don't spend more than our balance
        max_qty = (balance * 0.95) / entry_price  # 95% max of balance
        quantity = min(quantity, max_qty)

        logger.info(
            f"📐 Position Sizing | Balance: {balance:.2f} USDT | "
            f"Risk: {risk_amount:.2f} USDT | Qty: {quantity:.6f} BTC"
        )
        return round(quantity, 6)

    def is_safe_to_trade(self, min_balance_usdt=10.0):
        """Check if balance is enough to trade"""
        balance = self.get_usdt_balance()
        if balance < min_balance_usdt:
            logger.warning(f"⚠️  Balance too low: {balance:.2f} USDT (min: {min_balance_usdt})")
            return False
        return True
