import asyncio
import sys
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Static, RichLog

from config import SYMBOL, TIMEFRAME, LIMIT, RISK_AMOUNT
from exchange import (
    fetch_futures_klines,
    fetch_symbol_rules,
    fetch_account_info,
    place_market_order,
    close_position_market,
)
from indicators import calculate_indicators
from strategy import check_signal
from risk import calculate_quantity, round_to_step


class BotTUI(App):
    TITLE = "Binance Futures Bot"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen {
        layout: vertical;
    }

    .info-grid {
        height: auto;
        dock: top;
    }

    .info-box {
        border: solid $primary;
        padding: 1;
        margin: 0 1;
        height: auto;
    }

    .info-box Static {
        width: 100%;
    }

    #status-box {
        border: solid $secondary;
        padding: 1;
        margin: 0 1;
        height: auto;
    }

    #trade-box {
        border: solid $success;
        padding: 1;
        margin: 0 1;
        min-height: 5;
        height: auto;
    }

    RichLog {
        border: solid $accent;
        margin: 0 1;
        height: 1fr;
    }

    #balance-label {
        text-style: bold;
    }

    #candle-label {
        text-style: bold;
    }

    .label {
        text-style: bold;
        margin-bottom: 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(classes="info-grid"):
            with Vertical(id="balance-box", classes="info-box"):
                yield Static("ACCOUNT", classes="label")
                yield Static("Wallet: --- USDT", id="balance-wallet")
                yield Static("Available: --- USDT", id="balance-avail")
            with Vertical(id="candle-box", classes="info-box"):
                yield Static("CURRENT CANDLE", classes="label")
                yield Static("Waiting...", id="candle-data")
        with Vertical(id="status-box"):
            yield Static("STATUS", classes="label")
            yield Static("Starting bot...", id="status-text")
        with Vertical(id="trade-box"):
            yield Static("TRADE PLAN / POSITION", classes="label")
            yield Static("No active trade", id="trade-text")
        yield RichLog(id="log", highlight=True, max_lines=200)
        yield Footer()

    def add_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.query_one("#log", RichLog).write(f"[dim]{ts}[/] {msg}")

    def set_status(self, msg: str):
        self.query_one("#status-text", Static).update(msg)

    def set_trade(self, msg: str):
        self.query_one("#trade-text", Static).update(msg)

    def set_candle(self, d: dict):
        text = (
            f"O: {d['open']}  H: {d['high']}\n"
            f"L: {d['low']}  C: {d['close']}\n"
            f"ATR: {d['atr']}  Vol: {d['volume']}\n"
            f"BB U: {d['bb_upper']}\n"
            f"BB M: {d['bb_middle']}\n"
            f"BB L: {d['bb_lower']}"
        )
        self.query_one("#candle-data", Static).update(text)

    def update_balance(self, wallet: str, avail: str):
        self.query_one("#balance-wallet", Static).update(f"Wallet: {wallet} USDT")
        self.query_one("#balance-avail", Static).update(f"Available: {avail} USDT")

    async def bot_loop(self):
        try:
            tick_size, step_size = fetch_symbol_rules(SYMBOL)
            account = fetch_account_info()
            self.update_balance(
                account["totalWalletBalance"],
                account["availableBalance"]
            )
            self.add_log("Connected successfully")
        except Exception as e:
            self.add_log(f"[red]Connection error: {e}[/]")
            return

        last_checked_candle = None
        pending_order = None
        active_trade = None
        balance_ticks = 0

        self.set_status("Waiting for signal...")

        while True:
            try:
                df = fetch_futures_klines(SYMBOL, TIMEFRAME, LIMIT)
                df = calculate_indicators(df)

                candle = df.iloc[-1]
                last_closed = df.iloc[-2]

                self.set_candle({
                    "open": candle["open"],
                    "high": candle["high"],
                    "low": candle["low"],
                    "close": candle["close"],
                    "volume": candle["volume"],
                    "atr": f"{last_closed['atr']:.2f}",
                    "bb_upper": f"{last_closed['bb_upper']:.1f}",
                    "bb_middle": f"{last_closed['bb_middle']:.1f}",
                    "bb_lower": f"{last_closed['bb_lower']:.1f}",
                })

                current_price = float(candle["close"])

                # --- Manual stop entry ---
                if pending_order:
                    should_cancel = False

                    if pending_order["side"] == "BUY":
                        if current_price <= pending_order["sl"]:
                            should_cancel = True
                        elif current_price >= pending_order["entry"]:
                            self.add_log(f"Entry price reached ({pending_order['entry']}). Placing MARKET BUY...")
                            order = place_market_order(SYMBOL, "BUY", pending_order["quantity"])
                            self.add_log(f"Entry filled: {order['orderId']}")
                            active_trade = {
                                "side": pending_order["side"],
                                "entry": pending_order["entry"],
                                "sl": pending_order["sl"],
                                "tp": pending_order["tp"],
                            }
                            pending_order = None
                            account = fetch_account_info()
                            self.update_balance(account["totalWalletBalance"], account["availableBalance"])
                            self.set_status("Position opened")
                            self.set_trade(f"[green]BUY[/] open | Entry: {active_trade['entry']} | SL: {active_trade['sl']} | TP: {active_trade['tp']}")
                            continue

                    elif pending_order["side"] == "SELL":
                        if current_price >= pending_order["sl"]:
                            should_cancel = True
                        elif current_price <= pending_order["entry"]:
                            self.add_log(f"Entry price reached ({pending_order['entry']}). Placing MARKET SELL...")
                            order = place_market_order(SYMBOL, "SELL", pending_order["quantity"])
                            self.add_log(f"Entry filled: {order['orderId']}")
                            active_trade = {
                                "side": pending_order["side"],
                                "entry": pending_order["entry"],
                                "sl": pending_order["sl"],
                                "tp": pending_order["tp"],
                            }
                            pending_order = None
                            account = fetch_account_info()
                            self.update_balance(account["totalWalletBalance"], account["availableBalance"])
                            self.set_status("Position opened")
                            self.set_trade(f"[red]SELL[/] open | Entry: {active_trade['entry']} | SL: {active_trade['sl']} | TP: {active_trade['tp']}")
                            continue

                    if should_cancel:
                        self.add_log("[yellow]Pending order cancelled: price touched SL before entry[/]")
                        self.set_status("Waiting for signal...")
                        self.set_trade("No active trade")
                        pending_order = None
                        continue

                # --- Manual SL/TP & trailing ---
                if active_trade:
                    hit_sl = False
                    hit_tp = False

                    if active_trade["side"] == "BUY":
                        if current_price <= active_trade["sl"]:
                            hit_sl = True
                        elif current_price >= active_trade["tp"]:
                            hit_tp = True
                    elif active_trade["side"] == "SELL":
                        if current_price >= active_trade["sl"]:
                            hit_sl = True
                        elif current_price <= active_trade["tp"]:
                            hit_tp = True

                    if hit_sl:
                        self.add_log(f"[red]SL hit ({active_trade['sl']}). Closing...[/]")
                        close_position_market(SYMBOL)
                        self.add_log("Position closed by SL")
                        active_trade = None
                        account = fetch_account_info()
                        self.update_balance(account["totalWalletBalance"], account["availableBalance"])
                        self.set_status("Waiting for signal...")
                        self.set_trade("No active trade")
                        continue

                    if hit_tp:
                        self.add_log(f"[green]TP hit ({active_trade['tp']}). Closing...[/]")
                        close_position_market(SYMBOL)
                        self.add_log("Position closed by TP")
                        active_trade = None
                        account = fetch_account_info()
                        self.update_balance(account["totalWalletBalance"], account["availableBalance"])
                        self.set_status("Waiting for signal...")
                        self.set_trade("No active trade")
                        continue

                    # Trailing SL
                    current_atr = float(last_closed["atr"])
                    trail_distance = current_atr * 0.2

                    if active_trade["side"] == "BUY":
                        new_sl = current_price - trail_distance
                        if new_sl > active_trade["sl"]:
                            active_trade["sl"] = round_to_step(new_sl, tick_size)
                            self.set_trade(f"[green]BUY[/] Trailing SL: {active_trade['sl']} | TP: {active_trade['tp']}")
                            self.add_log(f"Trailing SL updated: {active_trade['sl']}")
                    elif active_trade["side"] == "SELL":
                        new_sl = current_price + trail_distance
                        if new_sl < active_trade["sl"]:
                            active_trade["sl"] = round_to_step(new_sl, tick_size)
                            self.set_trade(f"[red]SELL[/] Trailing SL: {active_trade['sl']} | TP: {active_trade['tp']}")
                            self.add_log(f"Trailing SL updated: {active_trade['sl']}")

                # --- New candle signal check ---
                current_open_time = int(candle["open_time"])

                if current_open_time != last_checked_candle and not pending_order and not active_trade:
                    last_checked_candle = current_open_time

                    self.add_log("New candle opened. Checking signal...")
                    self.set_status("Checking signal...")

                    signal = check_signal(df)

                    if signal:
                        quantity = calculate_quantity(
                            entry=signal["entry"],
                            sl=signal["sl"],
                            risk_amount=RISK_AMOUNT
                        )

                        signal["entry"] = round_to_step(signal["entry"], tick_size)
                        signal["sl"] = round_to_step(signal["sl"], tick_size)
                        signal["tp"] = round_to_step(signal["tp"], tick_size)
                        signal["quantity"] = round_to_step(quantity, step_size)

                        self.add_log(f"[cyan]TRADE PLAN FOUND: {signal['side']}[/]")
                        self.add_log(f"  Entry: {signal['entry']} | SL: {signal['sl']} | TP: {signal['tp']} | Qty: {signal['quantity']}")

                        self.set_status(f"Pending {signal['side']} entry at {signal['entry']}")
                        self.set_trade(f"Pending [{'green' if signal['side'] == 'BUY' else 'red'}]{signal['side']}[/] | Entry: {signal['entry']} | SL: {signal['sl']} | TP: {signal['tp']} | Qty: {signal['quantity']}")

                        pending_order = {
                            "side": signal["side"],
                            "entry": signal["entry"],
                            "sl": signal["sl"],
                            "tp": signal["tp"],
                            "quantity": signal["quantity"],
                        }
                    else:
                        self.set_status("Waiting for signal...")

                # Periodic balance refresh (every 10 seconds)
                balance_ticks += 1
                if balance_ticks >= 10:
                    balance_ticks = 0
                    account = fetch_account_info()
                    self.update_balance(account["totalWalletBalance"], account["availableBalance"])

            except Exception as e:
                self.add_log(f"[red]Error: {e}[/]")

            await asyncio.sleep(1)

    async def on_mount(self):
        self.add_log("Connecting to Binance Futures Testnet...")
        asyncio.create_task(self.bot_loop())


if __name__ == "__main__":
    app = BotTUI()
    app.run()
