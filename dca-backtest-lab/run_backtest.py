"""Run the configurable monthly DCA backtest and write raw results to JSON."""

import argparse
import json
import time
from pathlib import Path

import requests


# ===== PARAMETERS =====
# (symbol, monthly_invest)
PAIRS = [
    ("BTCUSDT", 10),
    ("BNBUSDT", 10),
]

# Minimum USDT order size per pair. Orders below this amount are skipped.
# Set a pair's value to the actual Binance minimum plus a small safety margin.
MIN_ORDER_USDT = {
    "BTCUSDT": 10,
    "BNBUSDT": 10,
}

TP_MULTIPLIER = 1  # Sell when price reaches previous sell ATH * this value.
TP_PERCENTAGE = 0.20  # Position fraction to sell at take profit.

# (minimum drawdown from ATH %, reserve percentage to deploy)
# No extra reserve buy occurs at a fresh ATH.
DRAWDOWN_TIERS = [
    (0, 0),
    (10, 1),
    (20, 3),
    (30, 7),
    (40, 15),
    (50, 40),
]
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


def reinvest_rate(drawdown_pct):
    """Return the reserve percentage for the current ATH drawdown."""
    rate = 0
    for minimum_drawdown, percentage in DRAWDOWN_TIERS:
        if drawdown_pct >= minimum_drawdown:
            rate = percentage
    return rate


def run_backtest():
    monthly_total = sum(pair[1] for pair in PAIRS)
    missing_minimums = [symbol for symbol, _ in PAIRS if symbol not in MIN_ORDER_USDT]
    if missing_minimums:
        raise ValueError(f"Missing MIN_ORDER_USDT for: {', '.join(missing_minimums)}")
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
        symbol: {"units": 0.0, "ath": 0.0, "ath_sell": 0.0, "reinvest": 0.0}
        for symbol, _ in PAIRS
    }
    records = []
    events = []
    usdt = 0.0
    injected = 0.0

    for date in dates:
        usdt += monthly_total
        injected += monthly_total
        actions = []

        for symbol, monthly_invest in PAIRS:
            asset = state[symbol]
            candle = candle_by_date[symbol][date]
            close = candle["close"]

            previous_ath = asset["ath"] or close
            drawdown_pct = max(0.0, (1 - close / previous_ath) * 100)
            asset["reinvest"] = reinvest_rate(drawdown_pct)

            # Reserve is used only on red candles and scales with ATH drawdown.
            if candle["close"] < candle["open"] and asset["reinvest"] > 0:
                dip_amount = min(usdt * asset["reinvest"] / 100, usdt - monthly_total)
                if dip_amount >= MIN_ORDER_USDT[symbol]:
                    asset["units"] += dip_amount / close
                    usdt -= dip_amount
                    events.append({"date": date, "symbol": symbol, "type": "dip", "price": close, "amount": dip_amount, "drawdown_pct": drawdown_pct, "reinvest_pct": asset["reinvest"]})
                    actions.append(f"{symbol[:3]} dip ${dip_amount:.0f}")

            if monthly_invest >= MIN_ORDER_USDT[symbol] and usdt >= monthly_invest:
                asset["units"] += monthly_invest / close
                usdt -= monthly_invest
                events.append({"date": date, "symbol": symbol, "type": "buy", "price": close, "amount": monthly_invest})
                actions.append(f"{symbol[:3]} DCA ${monthly_invest:.0f}")

            asset["ath"] = max(asset["ath"], close)
            if asset["ath_sell"] == 0:
                asset["ath_sell"] = close
            elif close >= asset["ath_sell"] * TP_MULTIPLIER:
                sell_amount = asset["units"] * TP_PERCENTAGE * close
                if sell_amount >= MIN_ORDER_USDT[symbol]:
                    asset["units"] -= asset["units"] * TP_PERCENTAGE
                    usdt += sell_amount
                    asset["reinvest"] = 0.0
                    asset["ath_sell"] = asset["ath"]
                    events.append({"date": date, "symbol": symbol, "type": "sell", "price": close, "amount": sell_amount})
                    actions.append(f"{symbol[:3]} sell {TP_PERCENTAGE * 100:.0f}%")
                else:
                    actions.append(f"{symbol[:3]} sell skipped (${sell_amount:.2f} < ${MIN_ORDER_USDT[symbol]:.2f})")

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
                }
                for symbol, monthly_invest in PAIRS
            ],
            "monthly_total": monthly_total,
            "min_order_usdt": MIN_ORDER_USDT,
            "tp_multiplier": TP_MULTIPLIER,
            "tp_percentage": TP_PERCENTAGE,
            "drawdown_tiers": [
                {"minimum_drawdown_pct": minimum, "reserve_percentage": percentage}
                for minimum, percentage in DRAWDOWN_TIERS
            ],
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
