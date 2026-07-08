import time
import hmac
import hashlib
from urllib.parse import urlencode

import requests
import pandas as pd

from config import API_KEY, SECRET_KEY, BASE_URL


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
    headers = {"X-MBX-APIKEY": API_KEY}

    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()


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
    headers = {"X-MBX-APIKEY": API_KEY}

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
    headers = {"X-MBX-APIKEY": API_KEY}

    response = requests.delete(url, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_futures_klines(symbol: str, interval: str, limit: int = 1500):
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}

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


def fetch_account_info():
    return signed_get("/fapi/v2/account")


def fetch_position(symbol: str):
    positions = signed_get("/fapi/v2/positionRisk", {"symbol": symbol})
    for position in positions:
        if position["symbol"] == symbol:
            return position
    return None


def fetch_open_orders(symbol: str):
    return signed_get("/fapi/v1/openOrders", {"symbol": symbol})


def cancel_order(symbol: str, order_id: int):
    return signed_delete("/fapi/v1/order", {"symbol": symbol, "orderId": order_id})


def cancel_all_open_orders(symbol: str):
    open_orders = fetch_open_orders(symbol)
    for order in open_orders:
        cancel_order(symbol, order["orderId"])
    return len(open_orders)


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


def update_stop_loss(symbol: str, side: str, old_sl_order_id: int, new_sl_price: float):
    cancel_order(symbol, old_sl_order_id)
    return place_stop_loss(symbol=symbol, side=side, stop_price=new_sl_price)
