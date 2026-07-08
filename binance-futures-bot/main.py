import asyncio
from live_data import listen_kline


async def main():
    async for kline in listen_kline("btcusdt", "1m"):
        print(
            f"{kline['symbol']} {kline['interval']} | "
            f"O: {kline['open']} | H: {kline['high']} | "
            f"L: {kline['low']} | C: {kline['close']} | "
            f"Vol: {kline['volume']} | Closed: {kline['closed']}"
        )


asyncio.run(main())
