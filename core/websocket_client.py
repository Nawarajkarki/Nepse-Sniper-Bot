import asyncio
import orjson
import websockets
import logging
import httpx
from decimal import Decimal, ROUND_DOWN
from config.settings import WS_URL, MEMBER_CODE, TMS_BASE_URL
from core.order_placement import place_order
from core.database import get_all_enabled_symbols
import json
from core.session_manager import get_session_snapshot

import logging


log = logging.getLogger("WS")


def round_to_tick(p: float) -> float:
    return float(
        Decimal(str(p)).quantize(
            Decimal('0.1'),
            rounding=ROUND_DOWN
        )
    )

async def handle_single_stock(symbol: str, session_cookies: dict, xsrf_token: str, host_session_id: str, client: httpx.AsyncClient):
    from core.database import get_security, get_trade_config

    sec = await get_security(symbol)
    cfg = await get_trade_config(symbol)

    if not sec or not cfg or not cfg.enabled:
        log.warning(f"❌ {symbol} missing data or disabled — skipping")
        return

    exchange_id = sec.exchange_security_id
    pre_close = float(sec.last_pre_close or 0)
    quantity = cfg.quantity

    if not exchange_id or not pre_close:
        log.error(f"❌ {symbol} missing exchange_id or pre_close")
        return

    circuit_limit = round_to_tick(pre_close * 1.15)
    previous_ltp = None
    
    session = await get_session_snapshot()
    cookie_header = session.get("cookie_header")
    
    headers = {
        "Cookie": cookie_header,
        "Origin": TMS_BASE_URL,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.5",
    }
    


    while True:
        try:
            async with websockets.connect(
                WS_URL,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10,
                max_size=None
            ) as ws:

                await ws.send(json.dumps({
                    "header": {
                        "channel": "@control", 
                        "transaction": "start_stockquote"
                    },
                    "payload": {
                        "argument": str(exchange_id)
                    }
                }))
                log.info(f"{symbol} subscribed (exch_id={exchange_id})")

                async for message in ws:
                    try:
                        try:
                            data = orjson.loads(message)
                        except orjson.JSONDecodeError:
                            continue

                        # NEW: Handle both single message AND batched list
                        if isinstance(data, list):
                            messages = data
                        else:
                            messages = [data]

                        for msg in messages:
                            try:
                                header = msg.get("header", {})
                                if header.get("channel") != "@data":
                                    continue
                                
                                
                                channel = header.get("channel", "unknown")

                                #  Show EVERY message types
                                if channel == "@control":
                                    log.debug(f"{symbol} ← @control: {msg.get('payload', {})}")
                                    continue
                                elif channel == "@heartbeat":
                                    log.debug(f"{symbol} ♥ heartbeat")
                                    continue
                                elif channel != "@data":
                                    log.debug(f"{symbol} ← unknown channel: {channel}")
                                    continue
                
                
                                # REAL @data message
                                quote = msg["payload"]["data"][0]
                                ltp = float(quote.get("ltp") or 0)
                                high = float(quote.get("dh", ltp))
                                low = float(quote.get("dl", ltp))
                                volume = int(quote.get("tv", 0))


                                if ltp != previous_ltp:
                                    if previous_ltp is not None and ltp > previous_ltp:
                                        price = min(round_to_tick(ltp * 1.02), circuit_limit)
                                        asyncio.create_task(place_order(symbol, price, quantity, session_cookies, xsrf_token, host_session_id, client=client))
                                        log.info(f"{symbol} ↑ LTP {previous_ltp:.1f} → {ltp:.1f} | High: {high:.1f} | Vol: {volume:,}")
                                    elif previous_ltp is not None:
                                        log.info(f"{symbol} ↓ LTP {previous_ltp:.1f} → {ltp:.1f} | High: {high:.1f}")
                                    else:
                                        # First tick
                                        log.info(f"{symbol} ● First Tick: {ltp:.1f}")

                                    previous_ltp = ltp
                                else:
                                    # Same LTP — still show every 10 seconds so we know it's alive
                                    if not hasattr(handle_single_stock, "last_debug"):
                                        handle_single_stock.last_debug = {}
                                    last = handle_single_stock.last_debug.get(symbol, 0)
                                    now = asyncio.get_event_loop().time()
                                    if now - last > 10:  # every 10 seconds
                                        log.info(f"{symbol} ● LTP stable @ {ltp:.1f} | High: {high:.1f} | Vol: {volume:,}")
                                        handle_single_stock.last_debug[symbol] = now
                        
                        
                                previous_ltp = ltp

                            except (KeyError, IndexError, ValueError, TypeError):
                                continue 
                                
        
                    except (KeyError, ValueError, json.JSONDecodeError):
                        continue

        except (websockets.ConnectionClosed, OSError, ConnectionResetError) as e:
            log.warning(f"{symbol} WS disconnected ({e}) — reconnecting in 3s...")
            await asyncio.sleep(3)
        except Exception as e:
            log.exception(f"{symbol} unexpected error: {e}")
            await asyncio.sleep(5)


async def start_all_websocket_clients(session_data: dict):
    cookies = session_data["cookies"]
    xsrf = session_data["xsrf_token"]
    host_session_id = session_data["host_session_id"]

    results = await get_all_enabled_symbols()
    
    log.info(f"Launching {len(results)} websocket clients — LIVE SNIPING")

    # Create ONE shared client for all order placements
    async with httpx.AsyncClient(timeout=10.0, http2=True) as client:
        tasks = [
            handle_single_stock(item["symbol"], cookies, xsrf, host_session_id, client)
            for item in results
        ]
        await asyncio.gather(*tasks, return_exceptions=True)