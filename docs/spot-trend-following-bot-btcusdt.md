BTCUSDT Spot Trend Following Strategy v1.0
Market
Symbol: BTCUSDT
Market: Spot
Timeframe: 4H
One trade at a time
Long only
Indicators
Indicator	Period	Purpose
EMA	50	Dynamic support
EMA	200	Long-term trend
ADX	14	Trend strength
ATR	14	Stop & trailing
RSI	14	Pullback quality
State 1 — Trend Detection

A trend is VALID only if all are true:

Close > EMA200

EMA50 > EMA200

ADX >= 25

Otherwise:

NO TRADE
State 2 — Wait for Pullback

Once a trend is valid, wait until:

Low <= EMA50

AND

Close > EMA200

This means price has retraced but the trend is still intact.

State 3 — Pullback Quality Filter

During the pullback:

40 <= RSI <= 60

Reject if:

RSI < 40

or

RSI > 60
State 4 — Entry Trigger

After a valid pullback:

Enter only on a NEW candle if:

Current Close > Previous Candle High

AND

Current Close > EMA50

Execute:

BUY MARKET
Position Size

User defines:

Risk = $10

Calculate

StopDistance = EntryPrice - StopPrice

Position Size

Quantity = RiskUSDT / StopDistance

Example

Risk = $10

Entry = 100000

Stop = 99500

Risk Distance = 500

Quantity = 10 / 500

= 0.02 BTC
Stop Loss

Calculate

ATR = ATR(14)

Stop candidate 1

Swing Low

Stop candidate 2

Entry - (2 × ATR)

Final stop

Lowest of the two

This gives the trade enough room to breathe.

Trade Management
At 1R Profit
Move Stop

↓

Entry Price

Risk becomes zero.

At 2R Profit

Enable trailing stop.

Trailing Stop

Highest Close

-

2 × ATR

Update every new 4H candle.

Never move the stop downward.

Exit Conditions

Exit immediately if any condition is true.

1. Stop Loss

Price reaches stop.

2. ATR Trailing Stop

Price closes below trailing stop.

3. Trend Reversal
EMA50 < EMA200

Close position.

4. Daily Trend Break
Daily Close < Daily EMA200

Close position.

Skip Trade Rules

Do not open a trade if any of these are true:

ADX < 25
ATR < ATR SMA(50)

(Low volatility)

Price > EMA50 + (2 × ATR)

(Already overextended)

Existing position is open.
Trading Loop

Every new 4H candle:

Update Indicators

↓

Already in Trade?

YES
    ↓
Manage Trade

NO
    ↓
Trend Valid?

NO
    ↓
Wait

YES
    ↓
Pullback?

NO
    ↓
Wait

YES
    ↓
RSI Valid?

NO
    ↓
Wait

YES
    ↓
Break Previous High?

NO
    ↓
Wait

YES
    ↓
Calculate Position Size

↓

Place Market Buy

↓

Place Stop Loss

↓

Manage Trade
Bot Parameters (User Configurable)
symbol: BTCUSDT

timeframe: 4h

risk_usdt: 10

ema_fast: 50

ema_slow: 200

adx_period: 14

adx_min: 25

atr_period: 14

atr_stop_multiplier: 2.0

atr_trailing_multiplier: 2.0

rsi_period: 14

rsi_min: 40

rsi_max: 60

one_trade_only: true

market_type: spot
Why this strategy?

This design follows a simple sequence:

Trade only in strong uptrends (EMA + ADX).
Wait patiently for a pullback instead of chasing price.
Require confirmation that buyers have regained control before entering.
Size the position from a fixed USDT risk, so every trade risks the same dollar amount.
Let winners run with an ATR-based trailing stop while cutting losses quickly.

This approach is straightforward to implement, minimizes subjective decisions, and is well suited for systematic testing and refinement before considering additional filters or optimizations.