import time

from config import SYMBOL, TIMEFRAME, LIMIT, RISK_AMOUNT
from exchange import (
    fetch_futures_klines,
    fetch_symbol_rules,
    fetch_account_info,
    fetch_position,
    cancel_order,
    cancel_all_open_orders,
    place_stop_entry_order,
    place_stop_loss,
    place_take_profit,
    update_stop_loss,
)
from indicators import calculate_indicators
from strategy import check_signal
from risk import calculate_quantity, round_to_step


def should_cancel_pending_order(pending_order, current_price: float):
    if pending_order["side"] == "BUY":
        return current_price <= pending_order["sl"]
    if pending_order["side"] == "SELL":
        return current_price >= pending_order["sl"]
    return False


def calculate_trailing_sl(active_trade, current_price: float, atr: float):
    trail_distance = atr * 0.2
    if active_trade["side"] == "BUY":
        new_sl = current_price - trail_distance
        if new_sl > active_trade["sl"]:
            return new_sl
    if active_trade["side"] == "SELL":
        new_sl = current_price + trail_distance
        if new_sl < active_trade["sl"]:
            return new_sl
    return None


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

    if pending_order:
        if should_cancel_pending_order(pending_order, current_price):
            result = cancel_order(SYMBOL, pending_order["order_id"])
            print("Pending order cancelled because price touched SL before entry")
            print(result)

            pending_order = None
            continue

        position = fetch_position(SYMBOL)
        position_amount = float(position["positionAmt"])

        if position_amount != 0:
            print("Entry filled. Position opened.")

            sl_order = place_stop_loss(
                symbol=SYMBOL,
                side=pending_order["side"],
                stop_price=pending_order["sl"]
            )

            tp_order = place_take_profit(
                symbol=SYMBOL,
                side=pending_order["side"],
                take_profit_price=pending_order["tp"]
            )

            active_trade = {
                "side": pending_order["side"],
                "entry": pending_order["entry"],
                "sl": pending_order["sl"],
                "tp": pending_order["tp"],
                "sl_order_id": sl_order["orderId"],
                "tp_order_id": tp_order["orderId"],
            }

            print("SL placed:", sl_order["orderId"])
            print("TP placed:", tp_order["orderId"])

            pending_order = None
            continue

    if active_trade:
        position = fetch_position(SYMBOL)
        position_amount = float(position["positionAmt"])

        if position_amount == 0:
            cancelled_count = cancel_all_open_orders(SYMBOL)

            print("Position closed.")
            print("Remaining open orders cancelled:", cancelled_count)

            active_trade = None
            continue

        current_atr = float(df.iloc[-2]["atr"])

        new_sl = calculate_trailing_sl(
            active_trade=active_trade,
            current_price=current_price,
            atr=current_atr
        )

        if new_sl:
            new_sl = round_to_step(new_sl, tick_size)

            sl_order = update_stop_loss(
                symbol=SYMBOL,
                side=active_trade["side"],
                old_sl_order_id=active_trade["sl_order_id"],
                new_sl_price=new_sl
            )

            active_trade["sl"] = new_sl
            active_trade["sl_order_id"] = sl_order["orderId"]

            print("Trailing SL updated:", new_sl)

    current_open_time = get_last_open_time(df)

    if current_open_time != last_checked_candle:
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
            print("Entry:", signal["entry"])
            print("SL:", signal["sl"])
            print("TP:", signal["tp"])
            print("Quantity:", signal["quantity"])
            print("Risk: $", RISK_AMOUNT)

            order = place_stop_entry_order(
                symbol=SYMBOL,
                side=signal["side"],
                quantity=signal["quantity"],
                stop_price=signal["entry"]
            )

            print("STOP ENTRY ORDER PLACED")
            print(order)

            pending_order = {
                "order_id": order["orderId"],
                "side": signal["side"],
                "entry": signal["entry"],
                "sl": signal["sl"],
                "tp": signal["tp"],
            }

        else:
            print("No trade signal")

    time.sleep(1)
