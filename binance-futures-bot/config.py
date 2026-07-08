from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY")
SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")