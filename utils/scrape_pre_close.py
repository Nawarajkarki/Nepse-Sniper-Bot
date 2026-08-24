from typing import Dict
import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import List, Optional

from core.database import *

BASE_URL = "https://www.sharesansar.com/company/{}"


async def fetch_pre_close(client: httpx.AsyncClient, symbol: str) -> Optional[float]:
    url = BASE_URL.format(symbol)

    try:
        print(f'fetching pre-close for {symbol} from {url}')
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        price_span = soup.find(
            "span",
            class_="text-comp-green comp-price padding-second",
        )

        if not price_span:
            price_span = soup.find(
                "span",
                class_="text-comp-red comp-price padding-second",
            )
            if not price_span:
                return None

        # Extract only the numeric text (strip icons, whitespace)
        price_text = price_span.get_text(strip=True)
        price = float(price_text)

        print(f'Fetched pre-close for {symbol}: {price}')
        return price

    except Exception as e:
        # log here if you have logging configured
        # logger.warning(f"Failed to fetch {symbol}: {e}")
        return None


async def update_all_pre_close_prices():
    symbols: List[str] = await get_all_trade_config_symbols()

    print(f"symbols - {symbols}")
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    async with httpx.AsyncClient(headers=headers) as client:
        tasks = [
            fetch_pre_close(client, symbol)
            for symbol in symbols
        ]

        results = await asyncio.gather(*tasks, return_exceptions=False)

        for symbol, price in zip(symbols, results):
            if price is None:
                continue

            result = update_pre_close_and_circuit_price(symbol=symbol, price=price)
            if asyncio.iscoroutine(result):
                await result



async def update_only_enabled_symbols_preclose():
    enabled_symbols: List[Dict] = await get_all_enabled_symbols()

    symbols = [item["symbol"] for item in enabled_symbols]

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    async with httpx.AsyncClient(headers=headers) as client:
        tasks = [
            fetch_pre_close(client, symbol)
            for symbol in symbols
        ]

        results = await asyncio.gather(*tasks, return_exceptions=False)

        for symbol, price in zip(symbols, results):
            if price is None:
                continue

            result = update_pre_close_and_circuit_price(symbol=symbol, price=price)
            if asyncio.iscoroutine(result):
                await result



if __name__ == "__main__":
    asyncio.run(update_only_enabled_symbols_preclose())
    
    
    