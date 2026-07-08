# How to Build a Cryptocurrency Futures Trading Bot

A comprehensive guide based on the `wayward-bot` template — a working Binance Futures trading bot that detects signals using Bollinger Bands and ATR, manages risk, and executes trades on the Binance Futures Testnet.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Project Structure](#2-project-structure)
3. [Step 1: Configuration](#3-step-1-configuration)
4. [Step 2: Exchange Layer (API Client)](#4-step-2-exchange-layer-api-client)
5. [Step 3: Indicator Calculation](#5-step-3-indicator-calculation)
6. [Step 4: Strategy / Signal Detection](#6-step-4-strategy--signal-detection)
7. [Step 5: Risk Management & Position Sizing](#7-step-5-risk-management--position-sizing)
8. [Step 6: The Bot Loop (Main Controller)](#8-step-6-the-bot-loop-main-controller)
9. [Step 7: Terminal UI (Optional)](#9-step-7-terminal-ui-optional)
10. [The Complete Trade Cycle](#10-the-complete-trade-cycle)
11. [Adapting This Template for Any Strategy](#11-adapting-this-template-for-any-strategy)
12. [Going to Mainnet](#12-going-to-mainnet)
13. [Next Steps & Improvements](#13-next-steps--improvements)

---

## 1. Architecture Overview

Every trading bot has the same fundamental pipeline:

```
Market Data → Indicators → Strategy → Risk → Execution → Monitoring
```

Each stage is an independent module with a single responsibility. This is the key to making bots that are easy to debug, adapt, and extend.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        BOT LOOP (main.py)                            │
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐         │
│  │ Fetch    │ → │ Calc     │ → │ Check    │ → │ Risk     │         │
│  │ Klines   │   │ Indica-  │   │ Signal   │   │ Mgmt     │         │
│  │ (Market  │   │ tors     │   │ (Strat-  │   │ (Position│         │
│  │ Data)    │   │ (ATR,BB) │   │ egy)     │   │ Sizing)  │         │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘         │
│                                                      │              │
│                                                      ▼              │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐         │
│  │ Monitor  │ ← │ Manage   │ ← │ Place    │ ← │ Execute  │         │
│  │ SL/TP    │   │ Trailing │   │ Order    │   │ (MARKET) │         │
│  │ (Price)  │   │ SL       │   │ (Manual  │   │          │         │
│  │          │   │          │   │  Entry)  │   │          │         │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘         │
└─────────────────────────────────────────────────────────────────────┘
```

**Key design principles used in this template:**

- **Config-driven:** All settings (symbol, timeframe, risk, API keys) live in one file.
- **Separation of concerns:** Exchange logic, indicators, strategy, risk, and the bot loop are separate files.
- **Manual execution fallback:** The testnet does not support `STOP_MARKET` orders, so entry/SL/TP are done by polling price + MARKET orders. The same architecture works on mainnet — you just swap in real stop orders.
- **New-candle signal detection:** Signals are checked only once per new candle (to avoid repainting), but price is polled every second for entry/SL/TP.

---

## 2. Project Structure

```
wayward-bot/
├── .env                  # API keys (never commit this!)
├── config.py             # All bot settings
├── exchange.py           # Binance API client (signed/unsigned)
├── indicators.py         # Technical indicator calculations
├── strategy.py           # Signal generation logic
├── risk.py               # Position sizing & rounding
├── main.py               # Bot loop (headless)
├── app.py                # Bot loop with Terminal UI (Textual)
└── requirements.txt      # Dependencies
```

Each file maps to exactly one stage of the pipeline. If you want to change exchanges (e.g. Coinbase, Bybit), you only touch `exchange.py`. If you want a different strategy, you only touch `strategy.py`.

---

## 3. Step 1: Configuration

`config.py` is the single source of truth for everything the bot needs to know.

```python
import os
from dotenv import load_dotenv

load_dotenv()

# Trading parameters
SYMBOL = "BTCUSFT"
TIMEFRAME = "1m"
LIMIT = 1500        # How many candles to fetch for indicator calculation

# Risk management
RISK_AMOUNT = 10    # $10 risk per trade

# Indicator parameters
ATR_PERIOD = 1000   # ATR lookback (long period for macro volatility)
BB_PERIOD = 20      # Bollinger Bands period
BB_STD = 2          # Standard deviations for BB

# API credentials (loaded from .env)
API_KEY = os.getenv("BINANCE_API_KEY")
SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

# Exchange endpoint
BASE_URL = "https://testnet.binancefuture.com"
```

**Important:** Never hardcode API keys. Use a `.env` file loaded via `python-dotenv`. Add `.env` to `.gitignore`.

---

## 4. Step 2: Exchange Layer (API Client)

`exchange.py` wraps all Binance Futures API calls. It has three types of functions:

### 4.1 Unsigned (Public) Requests

These don't need authentication — anyone can fetch market data.

```python
def fetch_futures_klines(symbol: str, interval: str, limit: int = 1500):
    """Fetch OHLCV candles from Binance Futures."""
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    response = requests.get(url, params=params, timeout=10)
    data = response.json()
    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume", ...
    ])
    df["open"] = df["open"].astype(float)    # Convert strings to floats
    return df
```

Also public: `fetch_symbol_rules()` retrieves `tickSize` (price precision) and `stepSize` (quantity precision) — critical for rounding.

### 4.2 Signed (Authenticated) Requests

These require your API key and a HMAC-SHA256 signature.

```
params → sorted query string → HMAC-SHA256(secret, query) → add signature
```

Three generic wrappers cover all authenticated endpoints:

- `signed_get(path, params)` — for account info, positions
- `signed_post(path, params)` — for placing orders
- `signed_delete(path, params)` — for cancelling orders

Example — placing a market order:

```python
def place_market_order(symbol: str, side: str, quantity: float):
    params = {
        "symbol": symbol,
        "side": side,           # "BUY" or "SELL"
        "type": "MARKET",
        "quantity": quantity,
    }
    return signed_post("/fapi/v1/order", params)
```

### 4.3 Endpoints Used

| Endpoint | Purpose |
|---|---|
| `GET /fapi/v1/klines` | Fetch historical candles |
| `GET /fapi/v1/exchangeInfo` | Get symbol rules (tickSize, stepSize) |
| `GET /fapi/v2/account` | Get wallet/available balance |
| `GET /fapi/v2/positionRisk` | Get current open positions |
| `POST /fapi/v1/order` | Place orders (MARKET, STOP_MARKET, etc.) |
| `DELETE /fapi/v1/order` | Cancel open orders |

**Note on `-4120` error:** Binance Futures Testnet does not support `STOP_MARKET` or `TAKE_PROFIT_MARKET` on `/fapi/v1/order`. They work on mainnet. For testnet, all stop logic must be implemented manually via price polling + MARKET orders.

---

## 5. Step 3: Indicator Calculation

`indicators.py` takes a DataFrame and adds computed columns. The template implements two indicators:

### 5.1 ATR (Average True Range)

Measures market volatility. Higher ATR = wider price swings.

```python
df["prev_close"] = df["close"].shift(1)

tr1 = df["high"] - df["low"]                    # Current bar range
tr2 = abs(df["high"] - df["prev_close"])         # Gap from prev close to high
tr3 = abs(df["low"] - df["prev_close"])          # Gap from prev close to low

df["true_range"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
df["atr"] = df["true_range"].rolling(period).mean()
```

**Why use ATR with a long period (1000)?** It measures macro volatility rather than micro noise, giving more stable SL/TP distances.

### 5.2 Bollinger Bands

Measures price relative to its recent average and volatility.

```python
df["bb_middle"] = df["close"].rolling(BB_PERIOD).mean()
df["bb_std"] = df["close"].rolling(BB_PERIOD).std()
df["bb_upper"] = df["bb_middle"] + BB_STD * df["bb_std"]
df["bb_lower"] = df["bb_middle"] - BB_STD * df["bb_std"]
```

### 5.3 Adding New Indicators

Simply add new columns to the DataFrame. For example, RSI:

```python
def calculate_rsi(df: pd.DataFrame, period: int = 14):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    return df
```

Then call it in the loop: `df = calculate_rsi(df)` and use `df.iloc[-2]["rsi"]` in your strategy.

---

## 6. Step 4: Strategy / Signal Detection

`strategy.py` has one function: `check_signal(df)`. It returns a trade plan dict or `None`.

### 6.1 The Template Strategy

Entry condition: The last closed candle closed outside the Bollinger Bands AND the candle range exceeded ATR (a "breakout with volatility").

```python
def check_signal(df):
    candle = df.iloc[-2]       # Last closed candle (not the forming one)
    candle_size = candle["high"] - candle["low"]

    buy_signal = candle["close"] < candle["bb_lower"] and candle_size > candle["atr"]
    sell_signal = candle["close"] > candle["bb_upper"] and candle_size > candle["atr"]
```

**Why `iloc[-2]`?** The last row (`-1`) is the forming candle. Using it would cause repainting — signals would change as the candle develops. Always use the fully closed candle.

### 6.2 Building the Trade Plan

When a signal fires, the strategy calculates entry, stop loss, and take profit:

```python
if buy_signal:
    entry = candle["close"] + candle["atr"] * 0.2   # Enter slightly above close
    sl = entry - candle["atr"]                        # 1 ATR below entry
    tp = candle["bb_middle"]                          # Mean reversion to BB middle

    return {
        "side": "BUY",
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "atr": candle["atr"],
    }
```

**Why offset entry by 0.2 × ATR?** To confirm the breakout. If price doesn't continue beyond the offset, the signal is weak.

### 6.3 Writing Your Own Strategy

Follow this pattern — just change the logic inside `check_signal(df)`:

```python
def check_signal(df):
    candle = df.iloc[-2]

    # Example: Golden cross strategy
    if candle["sma_50"] > candle["sma_200"] and df.iloc[-3]["sma_50"] <= df.iloc[-3]["sma_200"]:
        return {"side": "BUY", "entry": candle["close"], "sl": candle["close"] - 500, "tp": candle["close"] + 1000}

    return None
```

---

## 7. Step 5: Risk Management & Position Sizing

`risk.py` ensures you never risk more than your predefined amount per trade.

### 7.1 Position Sizing

The core formula:

```
risk_per_unit = abs(entry - sl)          # $ risk per unit of crypto
quantity = risk_amount / risk_per_unit   # How many units to trade
```

Example: Entry at 60000, SL at 59000, risk = $10
```
risk_per_unit = 1000 (USDT per BTC)
quantity = 10 / 1000 = 0.01 BTC
```

If SL is hit, you lose exactly $10 (minus fees).

### 7.2 Precision Rounding

Exchanges require prices and quantities to obey specific step sizes:

```python
def round_to_step(value: float, step: float):
    return round(value - (value % step), 10)
```

Always round your values using `tick_size` and `step_size` from `fetch_symbol_rules()`. A rejected order is almost always a precision error.

---

## 8. Step 6: The Bot Loop (Main Controller)

`main.py` ties everything together in an infinite polling loop. This is the heart of the bot.

### 8.1 Lifecycle

```
Initialize
  → fetch account info
  → fetch symbol rules (tick/step sizes)

Loop (every 1 second):
  1. Fetch latest klines
  2. Calculate indicators
  3. If pending entry order:
     - Monitor price → enter when price crosses entry level
     - Cancel if SL touched before entry
  4. If active trade:
     - Check SL / TP → close position if hit
     - Update trailing SL if price moves favorably
  5. If new candle AND no pending order AND no active trade:
     - Check signal
     - If signal found → create pending order
```

### 8.2 New Candle Detection

```python
current_open_time = int(df.iloc[-1]["open_time"])
if current_open_time != last_checked_candle:
    last_checked_candle = current_open_time
    # Check signal
```

This ensures you check for signals exactly once per candle, avoiding repainting.

### 8.3 Manual Stop Entry (Testnet Workaround)

Since the testnet doesn't support `STOP_MARKET`, the bot polls price and enters with a MARKET order when the entry level is reached:

```python
if pending_order:
    if side == "BUY" and current_price >= pending_order["entry"]:
        place_market_order(SYMBOL, "BUY", pending_order["quantity"])
        pending_order = None   # -> becomes active_trade
    elif current_price <= pending_order["sl"]:
        pending_order = None   # Cancel if SL hit before entry
```

### 8.4 Manual SL/TP Monitoring

Same approach — poll price, close with MARKET when triggered:

```python
if active_trade:
    if side == "BUY":
        if current_price <= active_trade["sl"]:  # SL hit
            close_position_market(SYMBOL, "BUY")
        elif current_price >= active_trade["tp"]: # TP hit
            close_position_market(SYMBOL, "BUY")
```

### 8.5 Trailing Stop Loss

The trailing SL moves with price in profit direction only:

```python
if active_trade["side"] == "BUY":
    new_sl = current_price - trail_distance  # trail_distance = ATR * 0.2
    if new_sl > active_trade["sl"]:          # Only move up
        active_trade["sl"] = new_sl
```

This locks in profits as price moves favorably, but never moves SL against you.

---

## 9. Step 7: Terminal UI (Optional)

`app.py` wraps the same bot loop in a [Textual](https://textual.textualize.io/) TUI for live monitoring.

### Architecture

```
|-- Textual App (BotTUI)
|   |-- compose(): Define layout (Static, RichLog widgets)
|   |-- on_mount(): Start bot_loop as background asyncio task
|   |   └── asyncio.create_task(self.bot_loop())
|   |-- bot_loop(): Same logic as main.py but updates widgets
```

Key difference from `main.py`: instead of `print()`, call `self.add_log()`, `self.set_status()`, `self.set_candle()`, etc. to update the UI widgets.

### Running

```bash
../.venv/bin/python app.py
```

Exit with **Ctrl+C**.

---

## 10. The Complete Trade Cycle

Here's exactly what happens from start to finish:

```
1. Bot starts
2. Fetches account info, symbol rules
3. Polls klines every 1s
4. New candle detected at open_time change
5. Strategy checks df.iloc[-2] (last closed candle)
6. Signal found: price closed below BB lower with high volatility
7. Trade plan: BUY at 60200, SL at 59200, TP at 60000, qty 0.001 BTC
8. Pending order created — bot starts monitoring
9. Price reaches 60200 → MARKET BUY executed immediately
10. Position opens → bot starts SL/TP/trailing monitoring
11. Price moves to 60500 → trailing SL moves from 59200 to 59400
12. Price moves to 61000 → trailing SL moves to 59600
13. Price drops to 59600 → SL hit → MARKET SELL closes position
14. Trade complete. Bot returns to checking for new signals.
```

---

## 11. Adapting This Template for Any Strategy

### 11.1 Change the Exchange

If switching from Binance to another exchange (Bybit, OKX, Coinbase):
1. Rewrite `exchange.py` with the new exchange's API
2. Keep the same function signatures: `fetch_futures_klines()`, `place_market_order()`, `close_position_market()`
3. No other files need changing

### 11.2 Change the Timeframe

Change `TIMEFRAME` in `config.py`:
- `"1m"` — 1 minute
- `"5m"` — 5 minutes
- `"15m"` — 15 minutes
- `"1h"` — 1 hour
- `"4h"` — 4 hours
- `"1d"` — daily

### 11.3 Change Indicators

Add new columns in `indicators.py`, use them in `strategy.py`.

### 11.4 Change the Strategy

Only touch `strategy.py`. Return the same dict structure:
```python
{"side": str, "entry": float, "sl": float, "tp": float, "atr": float}
```

### 11.5 Change Risk Parameters

Edit `RISK_AMOUNT` in `config.py`, or replace the sizing formula in `risk.py`.

---

## 12. Going to Mainnet

When switching from testnet to mainnet:

**config.py:**
```python
BASE_URL = "https://fapi.binance.com"  # Production endpoint
```

**API keys:** Use your real Binance API key with Futures permissions enabled.

**Stop orders:** `STOP_MARKET` and `TAKE_PROFIT_MARKET` work on mainnet's `/fapi/v1/order`. You can replace the manual polling in the bot loop with real stop orders:

```python
def place_stop_loss(symbol: str, side: str, stop_price: float, quantity: float):
    params = {
        "symbol": symbol,
        "side": side,
        "type": "STOP_MARKET",
        "stopPrice": stop_price,
        "closePosition": "true",
    }
    return signed_post("/fapi/v1/order", params)
```

---

## 13. Next Steps & Improvements

### Essential features to add before real trading:

1. **Logging to file** — `logging` module with rotation instead of `print()`
2. **Graceful shutdown** — Catch SIGINT/SIGTERM, close positions, save state
3. **Error recovery** — Retry on network errors, handle rate limits (HTTP 429)
4. **Backtesting** — Feed historical klines through `strategy.py` to evaluate performance
5. **Notifications** — Telegram/Discord/Slack webhooks for trade events

### Advanced features:

- **WebSocket** — Replace 1s polling with real-time WebSocket streams
- **Multiple symbols** — Run strategies on many pairs simultaneously
- **Portfolio risk** — Correlate positions across symbols, limit total exposure
- **Machine learning** — Use sklearn/XGBoost models as signal generators
- **Database** — Store all trades, candles, and P&L in SQLite/PostgreSQL
