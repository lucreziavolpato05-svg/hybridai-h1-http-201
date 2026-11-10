"""Passenger refund rules."""
import math

THRESHOLD_MIN = 60
HIGH_MIN = 120
MIN_PAYOUT_CHF = 5.0

def decide(delay_minutes: int, price_chf: float) -> dict:
    if isinstance(delay_minutes, bool) or not isinstance(delay_minutes, int) or delay_minutes < 0:
        raise ValueError("delay must be a non-negative integer")
    if isinstance(price_chf, bool) or not isinstance(price_chf, (int, float)) or not math.isfinite(price_chf) or price_chf <= 0:
        raise ValueError("price must be positive")
    percent = 50 if delay_minutes >= HIGH_MIN else 25 if delay_minutes >= THRESHOLD_MIN else 0
    amount = round(price_chf * percent / 100, 2)
    return {"status": "entitled" if percent else "notEntitled", "percent": percent,
            "amountChf": amount, "paidOut": bool(percent and amount >= MIN_PAYOUT_CHF),
            "rule": "from120" if percent == 50 else "from60" if percent else "under60",
            "minPayoutChf": MIN_PAYOUT_CHF, "thresholdMin": THRESHOLD_MIN}

def policy_tool(parameters):
    try:
        delay = parameters["delayMinutes"]
        price = parameters["price"]
        if isinstance(delay, bool) or isinstance(price, bool):
            raise ValueError
        delay = int(str(delay))
        price = float(price)
        return decide(delay, price), {"source": "refund policy, Sheet 2"}
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError("invalid delayMinutes or price") from None

TOOLS = {"_policy": policy_tool}
