import requests
import pandas as pd

SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"
LIMIT = 1500

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


df = fetch_futures_klines(SYMBOL, TIMEFRAME, LIMIT)
df = calculate_indicators(df)

last = df.iloc[-1]

print("Latest candle:")
print("Close:", last["close"])
print("ATR:", last["atr"])
print("BB Upper:", last["bb_upper"])
print("BB Middle:", last["bb_middle"])
print("BB Lower:", last["bb_lower"])