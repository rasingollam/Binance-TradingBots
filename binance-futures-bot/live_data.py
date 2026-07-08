import asyncio
import json
import websockets


def stream_url(symbol: str, interval: str) -> str:
    return f"wss://fstream.binance.com/market/ws/{symbol.lower()}@kline_{interval}"


async def listen_kline(symbol: str, interval: str = "1m"):
    url = stream_url(symbol, interval)
    async with websockets.connect(url) as ws:
        print(f"Connected to {symbol} {interval} futures kline stream")
        while True:
            message = await ws.recv()
            data = json.loads(message)
            kline = data["k"]
            yield {
                "symbol": symbol,
                "interval": interval,
                "open": kline["o"],
                "high": kline["h"],
                "low": kline["l"],
                "close": kline["c"],
                "volume": kline["v"],
                "closed": kline["x"],
            }
