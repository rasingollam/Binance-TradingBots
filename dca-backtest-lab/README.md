# DCA Backtest Lab

1. Edit the `PAIRS`, take-profit, and reinvestment settings at the top of `run_backtest.py`.
2. Generate raw backtest data:

```bash
python3 run_backtest.py
```

This writes only the configuration, monthly portfolio records, and trade events to `backtest-results.json`.

3. Start the interactive dashboard:

```bash
python3 -m http.server 8000
```

Open `http://localhost:8000` in a browser. The dashboard loads `backtest-results.json`, has interactive Plotly charts, and can also load any result JSON with the **Load JSON** button.
