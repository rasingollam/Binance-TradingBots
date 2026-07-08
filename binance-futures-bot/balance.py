from binance.client import Client
from config import API_KEY, SECRET_KEY

client = Client(API_KEY, SECRET_KEY, testnet=True)
account = client.futures_account()

print(f"{'Asset':<10} {'Available':>15}")
print("-" * 28)
for a in account["assets"]:
    avail = float(a["availableBalance"])
    if avail > 0:
        print(f"{a['asset']:<10} {avail:>15.4f}")
