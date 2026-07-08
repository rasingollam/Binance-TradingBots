import time

from config import SYMBOL, TIMEFRAME, LIMIT, RISK_AMOUNT
from exchange import (
    fetch_futures_klines,
    fetch_symbol_rules,
    fetch_account_info,
    fetch_position,
    place_market_order,
    close_position_market,
)
from indicators import calculate_indicators
from strategy import check_signal
from risk import calculate_quantity, round_to_step


def get_last_open_time(df):
    return int(df.iloc[-1]["open_time"])


account = fetch_account_info()

print("Connected to Binance Futures Testnet")
print("Total wallet balance:", account["totalWalletBalance"])
print("Available balance:", account["availableBalance"])

last_checked_candle = None
pending_order = None
active_trade = None

tick_size, step_size = fetch_symbol_rules(SYMBOL)

while True:
    df = fetch_futures_klines(SYMBOL, TIMEFRAME, LIMIT)
    df = calculate_indicators(df)

    current_price = float(df.iloc[-1]["close"])

    # --- Manual stop entry: wait for price to cross entry level ---
    if pending_order:
        should_cancel = False

        if pending_order["side"] == "BUY":
            if current_price <= pending_order["sl"]:
                should_cancel = True
            elif current_price >= pending_order["entry"]:
                print(f"\nEntry price reached ({pending_order['entry']}). Placing MARKET BUY...")
                order = place_market_order(SYMBOL, "BUY", pending_order["quantity"])
                print("Entry filled:", order["orderId"])
                pending_order = None
                continue

        elif pending_order["side"] == "SELL":
            if current_price >= pending_order["sl"]:
                should_cancel = True
            elif current_price <= pending_order["entry"]:
                print(f"\nEntry price reached ({pending_order['entry']}). Placing MARKET SELL...")
                order = place_market_order(SYMBOL, "SELL", pending_order["quantity"])
                print("Entry filled:", order["orderId"])
                pending_order = None
                continue

        if should_cancel:
            print("Pending order cancelled: price touched SL before entry")
            pending_order = None
            continue

    # --- Manual SL/TP & trailing for active trade ---
    if active_trade:
        hit_sl = False
        hit_tp = False

        if active_trade["side"] == "BUY":
            if current_price <= active_trade["sl"]:
                hit_sl = True
            elif current_price >= active_trade["tp"]:
                hit_tp = True
        elif active_trade["side"] == "SELL":
            if current_price >= active_trade["sl"]:
                hit_sl = True
            elif current_price <= active_trade["tp"]:
                hit_tp = True

        if hit_sl:
            print(f"\nSL hit ({active_trade['sl']}). Closing position...")
            close_position_market(SYMBOL)
            print("Position closed by SL")
            active_trade = None
            continue

        if hit_tp:
            print(f"\nTP hit ({active_trade['tp']}). Closing position...")
            close_position_market(SYMBOL)
            print("Position closed by TP")
            active_trade = None
            continue

        # Trailing SL
        current_atr = float(df.iloc[-2]["atr"])
        trail_distance = current_atr * 0.2

        if active_trade["side"] == "BUY":
            new_sl = current_price - trail_distance
            if new_sl > active_trade["sl"]:
                active_trade["sl"] = round_to_step(new_sl, tick_size)
                print("Trailing SL updated:", active_trade["sl"])
        elif active_trade["side"] == "SELL":
            new_sl = current_price + trail_distance
            if new_sl < active_trade["sl"]:
                active_trade["sl"] = round_to_step(new_sl, tick_size)
                print("Trailing SL updated:", active_trade["sl"])

    # --- New candle signal check ---
    current_open_time = get_last_open_time(df)

    if current_open_time != last_checked_candle and not pending_order and not active_trade:
        last_checked_candle = current_open_time

        print("\nNew candle opened. Checking signal...")

        signal = check_signal(df)

        if signal:
            quantity = calculate_quantity(
                entry=signal["entry"],
                sl=signal["sl"],
                risk_amount=RISK_AMOUNT
            )

            signal["entry"] = round_to_step(signal["entry"], tick_size)
            signal["sl"] = round_to_step(signal["sl"], tick_size)
            signal["tp"] = round_to_step(signal["tp"], tick_size)
            signal["quantity"] = round_to_step(quantity, step_size)

            print("TRADE PLAN FOUND")
            print("Side:", signal["side"])
            print("Waiting for entry at:", signal["entry"])
            print("SL:", signal["sl"])
            print("TP:", signal["tp"])
            print("Quantity:", signal["quantity"])
            print("Risk: $", RISK_AMOUNT)

            pending_order = {
                "side": signal["side"],
                "entry": signal["entry"],
                "sl": signal["sl"],
                "tp": signal["tp"],
                "quantity": signal["quantity"],
            }

        else:
            print("No trade signal")

    time.sleep(1)
