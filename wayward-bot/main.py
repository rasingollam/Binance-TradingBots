import requests
import pandas as pd

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


df = fetch_futures_klines(SYMBOL, TIMEFRAME, LIMIT)
df = calculate_indicators(df)

signal = check_signal(df)

if signal:
    quantity = calculate_quantity(
        entry=signal["entry"],
        sl=signal["sl"],
        risk_amount=RISK_AMOUNT
    )

    signal["quantity"] = quantity

    print("TRADE PLAN FOUND")
    print("Side:", signal["side"])
    print("Entry:", signal["entry"])
    print("SL:", signal["sl"])
    print("TP:", signal["tp"])
    print("ATR:", signal["atr"])
    print("Quantity:", signal["quantity"])
    print("Risk: $", RISK_AMOUNT)

else:
    print("No trade signal")