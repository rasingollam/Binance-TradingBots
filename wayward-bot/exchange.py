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
    if not response.ok:
        print("Binance API error:", response.text)
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
    fallback = None
    for position in positions:
        if position["symbol"] != symbol:
            continue

        fallback = position
        if float(position.get("positionAmt", 0)) != 0:
            return position

    return fallback


def fetch_order_history(symbol: str, limit: int = 10):
    return signed_get("/fapi/v1/allOrders", {"symbol": symbol, "limit": limit})


def cancel_order(symbol: str, order_id: int):
    return signed_delete("/fapi/v1/order", {"symbol": symbol, "orderId": order_id})


def place_market_order(symbol: str, side: str, quantity: float):
    params = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": quantity,
    }
    return signed_post("/fapi/v1/order", params)


def close_position_market(symbol: str):
    position = fetch_position(symbol)
    if not position:
        raise ValueError(f"No open position found for {symbol}")

    position_amt = float(position["positionAmt"])
    if position_amt == 0:
        raise ValueError(f"No open position found for {symbol}")

    # Binance returns positive quantity for longs and negative for shorts.
    close_side = "SELL" if position_amt > 0 else "BUY"
    params = {
        "symbol": symbol,
        "side": close_side,
        "type": "MARKET",
        "quantity": abs(position_amt),
        "reduceOnly": "true",
    }

    position_side = position.get("positionSide")
    if position_side and position_side != "BOTH":
        params["positionSide"] = position_side

    return signed_post("/fapi/v1/order", params)
