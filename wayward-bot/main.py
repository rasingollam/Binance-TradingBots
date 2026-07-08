import os
import time
import hmac
import hashlib
from urllib.parse import urlencode

import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY")
SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

BASE_URL = "https://testnet.binancefuture.com"

SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"
LIMIT = 1500

RISK_AMOUNT = 10

ATR_PERIOD = 1000
BB_PERIOD = 20
BB_STD = 2


def fetch_futures_klines(symbol: str, interval: str, limit: int = 1500):
    url = "https://fapi.binance.com/fapi/v1/klines"

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])

    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)

    return df


def calculate_indicators(df: pd.DataFrame):
    # ATR
    df["prev_close"] = df["close"].shift(1)

    df["tr1"] = df["high"] - df["low"]
    df["tr2"] = abs(df["high"] - df["prev_close"])
    df["tr3"] = abs(df["low"] - df["prev_close"])

    df["true_range"] = df[["tr1", "tr2", "tr3"]].max(axis=1)
    df["atr"] = df["true_range"].rolling(ATR_PERIOD).mean()

    # Bollinger Bands
    df["bb_middle"] = df["close"].rolling(BB_PERIOD).mean()
    df["bb_std"] = df["close"].rolling(BB_PERIOD).std()

    df["bb_upper"] = df["bb_middle"] + (BB_STD * df["bb_std"])
    df["bb_lower"] = df["bb_middle"] - (BB_STD * df["bb_std"])

    return df


def calculate_quantity(entry: float, sl: float, risk_amount: float):
    risk_per_unit = abs(entry - sl)

    if risk_per_unit <= 0:
        raise ValueError("Invalid entry/SL. Risk per unit must be greater than 0.")

    quantity = risk_amount / risk_per_unit
    return quantity


def fetch_symbol_rules(symbol: str):
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    response = requests.get(url, timeout=10)
    response.raise_for_status()

    data = response.json()

    for item in data["symbols"]:
        if item["symbol"] == symbol:
            tick_size = None
            step_size = None

            for f in item["filters"]:
                if f["filterType"] == "PRICE_FILTER":
                    tick_size = float(f["tickSize"])

                if f["filterType"] == "LOT_SIZE":
                    step_size = float(f["stepSize"])

            return tick_size, step_size

    raise ValueError(f"Symbol rules not found for {symbol}")


def signed_get(path: str, params=None):
    if params is None:
        params = {}

    params["timestamp"] = int(time.time() * 1000)

    query_string = urlencode(params)
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    url = f"{BASE_URL}{path}?{query_string}&signature={signature}"

    headers = {
        "X-MBX-APIKEY": API_KEY
    }

    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()

    return response.json()


def fetch_account_info():
    return signed_get("/fapi/v2/account")


def signed_post(path: str, params=None):
    if params is None:
        params = {}

    params["timestamp"] = int(time.time() * 1000)

    query_string = urlencode(params)
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    url = f"{BASE_URL}{path}?{query_string}&signature={signature}"

    headers = {
        "X-MBX-APIKEY": API_KEY
    }

    response = requests.post(url, headers=headers, timeout=10)
    response.raise_for_status()

    return response.json()


def signed_delete(path: str, params=None):
    if params is None:
        params = {}

    params["timestamp"] = int(time.time() * 1000)

    query_string = urlencode(params)
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    url = f"{BASE_URL}{path}?{query_string}&signature={signature}"

    headers = {
        "X-MBX-APIKEY": API_KEY
    }

    response = requests.delete(url, headers=headers, timeout=10)
    response.raise_for_status()

    return response.json()


def cancel_order(symbol: str, order_id: int):
    return signed_delete("/fapi/v1/order", {
        "symbol": symbol,
        "orderId": order_id,
    })


def fetch_position(symbol: str):
    positions = signed_get("/fapi/v2/positionRisk", {
        "symbol": symbol
    })

    for position in positions:
        if position["symbol"] == symbol:
            return position

    return None


def place_stop_loss(symbol: str, side: str, stop_price: float):
    close_side = "SELL" if side == "BUY" else "BUY"

    return signed_post("/fapi/v1/order", {
        "symbol": symbol,
        "side": close_side,
        "type": "STOP_MARKET",
        "stopPrice": stop_price,
        "closePosition": "true",
        "workingType": "MARK_PRICE",
    })


def place_take_profit(symbol: str, side: str, take_profit_price: float):
    close_side = "SELL" if side == "BUY" else "BUY"

    return signed_post("/fapi/v1/order", {
        "symbol": symbol,
        "side": close_side,
        "type": "TAKE_PROFIT_MARKET",
        "stopPrice": take_profit_price,
        "closePosition": "true",
        "workingType": "MARK_PRICE",
    })


def should_cancel_pending_order(pending_order, current_price: float):
    if pending_order["side"] == "BUY":
        return current_price <= pending_order["sl"]

    if pending_order["side"] == "SELL":
        return current_price >= pending_order["sl"]

    return False


def place_stop_entry_order(symbol: str, side: str, quantity: float, stop_price: float):
    order_side = "BUY" if side == "BUY" else "SELL"

    params = {
        "symbol": symbol,
        "side": order_side,
        "type": "STOP_MARKET",
        "quantity": quantity,
        "stopPrice": stop_price,
        "workingType": "MARK_PRICE",
    }

    return signed_post("/fapi/v1/order", params)


def update_stop_loss(symbol: str, side: str, old_sl_order_id: int, new_sl_price: float):
    cancel_order(symbol, old_sl_order_id)

    return place_stop_loss(
        symbol=symbol,
        side=side,
        stop_price=new_sl_price
    )


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


def round_to_step(value: float, step: float):
    return round(value - (value % step), 10)


def fetch_open_orders(symbol: str):
    return signed_get("/fapi/v1/openOrders", {
        "symbol": symbol
    })


def cancel_all_open_orders(symbol: str):
    open_orders = fetch_open_orders(symbol)

    for order in open_orders:
        cancel_order(symbol, order["orderId"])

    return len(open_orders)


def get_last_open_time(df: pd.DataFrame):
    return int(df.iloc[-1]["open_time"])


def check_signal(df: pd.DataFrame):
    candle = df.iloc[-2]

    candle_size = candle["high"] - candle["low"]

    buy_signal = (
        candle["close"] < candle["bb_lower"]
        and candle_size > candle["atr"] * 1
    )

    sell_signal = (
        candle["close"] > candle["bb_upper"]
        and candle_size > candle["atr"] * 1
    )

    if buy_signal:
        entry = candle["close"] + candle["atr"] * 0.2
        sl = entry - candle["atr"] * 1
        tp = candle["bb_middle"]

        return {
            "side": "BUY",
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "atr": candle["atr"],
            "close": candle["close"],
        }

    if sell_signal:
        entry = candle["close"] - candle["atr"] * 0.2
        sl = entry + candle["atr"] * 1
        tp = candle["bb_middle"]

        return {
            "side": "SELL",
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "atr": candle["atr"],
            "close": candle["close"],
        }

    return None


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