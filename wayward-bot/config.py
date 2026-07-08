import os
from dotenv import load_dotenv

load_dotenv()

SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"
LIMIT = 1500

RISK_AMOUNT = 10

ATR_PERIOD = 1000
BB_PERIOD = 20
BB_STD = 2

API_KEY = os.getenv("BINANCE_API_KEY")
SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

BASE_URL = "https://testnet.binancefuture.com"
