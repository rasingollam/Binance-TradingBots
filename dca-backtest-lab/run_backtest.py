"""Run the configurable monthly DCA backtest and write raw results to JSON."""

import argparse
import json
import time
from pathlib import Path

import requests


# ===== PARAMETERS =====
# (symbol, monthly_invest, reinvest_start_pct, reinvest_step_pct, reinvest_cap_pct)
PAIRS = [
    ("BTCUSDT", 10, 1, 2, 50),
    # ("BNBUSDT", 10, 1, 1, 40),
]

TP_MULTIPLIER = 1.5  # Sell when price reaches previous sell ATH * this value.
TP_PERCENTAGE = 0.35  # Position fraction to sell at take profit.
# ===== END PARAMETERS =====

KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_base", "taker_quote", "ignore",
]


def fetch_monthly_klines(symbol):
    """Fetch all available monthly Binance spot candles for one pair."""
    rows = []
    start_time = 0
    url = "https://api.binance.com/api/v3/klines"

    while True:
        response = requests.get(
            url,
            params={"symbol": symbol, "interval": "1M", "startTime": start_time, "limit": 500},
            timeout=30,
        )
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 500:
            break
        start_time = batch[-1][0] + 1
        time.sleep(0.1)

    return [
        {
            "date": time.strftime("%Y-%m-%d", time.gmtime(row[0] / 1000)),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
        }
        for row in rows
    ]


def run_backtest():
    monthly_total = sum(pair[1] for pair in PAIRS)
    candles = {symbol: fetch_monthly_klines(symbol) for symbol, *_ in PAIRS}

    common_dates = set(candle["date"] for candle in candles[PAIRS[0][0]])
    for symbol, *_ in PAIRS[1:]:
        common_dates &= {candle["date"] for candle in candles[symbol]}
    dates = sorted(common_dates)
    if not dates:
        raise RuntimeError("The selected pairs do not have a common monthly history.")

    candle_by_date = {
        symbol: {candle["date"]: candle for candle in series}
        for symbol, series in candles.items()
    }
    state = {
        symbol: {"units": 0.0, "ath": 0.0, "ath_sell": 0.0, "reinvest": float(start), "cap": float(cap)}
        for symbol, _, start, _, cap in PAIRS
    }
    records = []
    events = []
    usdt = 0.0
    injected = 0.0

    for date in dates:
        usdt += monthly_total
        injected += monthly_total
        actions = []

        for symbol, monthly_invest, start, step, cap in PAIRS:
            asset = state[symbol]
            candle = candle_by_date[symbol][date]
            close = candle["close"]

            # Reserve is deliberately used before the new monthly DCA allocation.
            if candle["close"] < candle["open"]:
                dip_amount = min(usdt * asset["reinvest"] / 100, usdt - monthly_total)
                if dip_amount > 5:
                    asset["units"] += dip_amount / close
                    usdt -= dip_amount
                    events.append({"date": date, "symbol": symbol, "type": "dip", "price": close, "amount": dip_amount})
                    actions.append(f"{symbol[:3]} dip ${dip_amount:.0f}")

            if usdt >= monthly_invest:
                asset["units"] += monthly_invest / close
                usdt -= monthly_invest
                events.append({"date": date, "symbol": symbol, "type": "buy", "price": close, "amount": monthly_invest})
                actions.append(f"{symbol[:3]} DCA ${monthly_invest:.0f}")

            asset["ath"] = max(asset["ath"], close)
            if asset["ath_sell"] == 0:
                asset["ath_sell"] = close
            elif close >= asset["ath_sell"] * TP_MULTIPLIER:
                sell_amount = asset["units"] * TP_PERCENTAGE * close
                asset["units"] -= asset["units"] * TP_PERCENTAGE
                usdt += sell_amount
                asset["reinvest"] = float(start)
                asset["ath_sell"] = asset["ath"]
                events.append({"date": date, "symbol": symbol, "type": "sell", "price": close, "amount": sell_amount})
                actions.append(f"{symbol[:3]} sell {TP_PERCENTAGE * 100:.0f}%")
            else:
                asset["reinvest"] = min(float(cap), asset["reinvest"] + float(step))

        positions = {}
        portfolio_value = usdt
        for symbol, *_ in PAIRS:
            close = candle_by_date[symbol][date]["close"]
            value = state[symbol]["units"] * close
            portfolio_value += value
            positions[symbol] = {
                "close": close,
                "units": state[symbol]["units"],
                "value": value,
                "reinvest_pct": state[symbol]["reinvest"],
            }

        records.append(
            {
                "date": date,
                "injected": injected,
                "usdt": usdt,
                "portfolio_value": portfolio_value,
                "positions": positions,
                "actions": actions,
            }
        )

    return {
        "version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {
            "pairs": [
                {
                    "symbol": symbol,
                    "monthly_invest": monthly_invest,
                    "reinvest_start_pct": start,
                    "reinvest_step_pct": step,
                    "reinvest_cap_pct": cap,
                }
                for symbol, monthly_invest, start, step, cap in PAIRS
            ],
            "monthly_total": monthly_total,
            "tp_multiplier": TP_MULTIPLIER,
            "tp_percentage": TP_PERCENTAGE,
        },
        "records": records,
        "events": events,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="backtest-results.json", help="Output JSON path")
    args = parser.parse_args()

    result = run_backtest()
    output = Path(args.output)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Saved {output} ({len(result['records'])} months, {len(result['events'])} events)")


if __name__ == "__main__":
    main()
