import pandas as pd
from config import ATR_PERIOD, BB_PERIOD, BB_STD


def calculate_indicators(df: pd.DataFrame):
    df["prev_close"] = df["close"].shift(1)

    tr1 = df["high"] - df["low"]
    tr2 = abs(df["high"] - df["prev_close"])
    tr3 = abs(df["low"] - df["prev_close"])

    df["true_range"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = df["true_range"].rolling(ATR_PERIOD).mean()

    df["bb_middle"] = df["close"].rolling(BB_PERIOD).mean()
    df["bb_std"] = df["close"].rolling(BB_PERIOD).std()
    df["bb_upper"] = df["bb_middle"] + BB_STD * df["bb_std"]
    df["bb_lower"] = df["bb_middle"] - BB_STD * df["bb_std"]

    return df
