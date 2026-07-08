def check_signal(df):
    candle = df.iloc[-2]
    candle_size = candle["high"] - candle["low"]

    buy_signal = (
        candle["close"] < candle["bb_lower"]
        and candle_size > candle["atr"]
    )

    sell_signal = (
        candle["close"] > candle["bb_upper"]
        and candle_size > candle["atr"]
    )

    if buy_signal:
        entry = candle["close"] + candle["atr"] * 0.2
        sl = entry - candle["atr"]
        tp = candle["bb_middle"]

        return {
            "side": "BUY",
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "atr": candle["atr"],
        }

    if sell_signal:
        entry = candle["close"] - candle["atr"] * 0.2
        sl = entry + candle["atr"]
        tp = candle["bb_middle"]

        return {
            "side": "SELL",
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "atr": candle["atr"],
        }

    return None
