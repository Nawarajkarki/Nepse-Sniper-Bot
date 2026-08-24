import asyncio
import logging
from datetime import datetime
import pytz
from typing import Optional
from decimal import Decimal

import httpx


from config.symbols import WATCHLIST
from utils.timing import sleep_and_free_program_at
from core.database import (
    get_security,
    has_first_order_executed,
    record_first_order_execution,
    get_all_trade_config_symbols,
    get_trade_config,
)
from core.order_placement import place_order

log = logging.getLogger("STARTUP_FIRST_ORDER")

NEPAL_TZ = pytz.timezone("Asia/Kathmandu")
RETRY_ATTEMPTS = 3
BACKOFF_SECS = [0.5, 1.0, 2.0]  # exponential backoff between retries

def round_to_tick(p: float) -> float:
    return float(Decimal(str(p)).quantize(Decimal('0.1')))

async def place_order_with_retries(
    symbol: str,
    price: float,
    quantity: int,
    cookies: dict,
    xsrf_token: str,
    host_session_id: str,
    client: httpx.AsyncClient,
) -> tuple[bool, dict]:
    """
    Attempt to place an order up to RETRY_ATTEMPTS times.
    Returns (success: bool, details: dict).
    """
    last_exc = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            success = await place_order(
                symbol=symbol,
                price=price,
                quantity=quantity,
                cookies=cookies,
                xsrf_token=xsrf_token,
                host_session_id=host_session_id,
                client=client,
            )
            if success:
                log.info(f"{symbol} → first order SUCCESS (attempt {attempt})")
                return True, {"attempt": attempt}

            log.warning(f"{symbol} → first order FAILED (attempt {attempt})")
            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(BACKOFF_SECS[attempt - 1])

        except Exception as e:
            log.error(f"{symbol} → first order EXCEPTION attempt {attempt}: {e}")
            last_exc = e
            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(BACKOFF_SECS[attempt - 1])

    return False, {"attempts": RETRY_ATTEMPTS, "last_error": str(last_exc)}


async def run_startup_first_orders(session: dict, watchlist: list = None) -> None:
    """
    Places first orders using MULTIPLE HTTP CLIENTS for true concurrent execution.
    
    Strategy:
    1. Pre-warm all HTTP connections with lightweight requests
    2. Fire all orders simultaneously with ZERO delay
    3. Each order gets its own HTTP client to avoid HTTP/2 stream conflicts
    
    Eligible symbols must have:
      - Both exchange_security_id and security_id in DB
      - last_pre_close price in DB
      - NOT already executed a first order today
    """
    if watchlist is None:
        watchlist = WATCHLIST

    now_nepal = datetime.now(NEPAL_TZ)
    log.info(f"Preparing startup first orders (Nepal time: {now_nepal.time()})")

    today = now_nepal.date().isoformat()  # YYYY-MM-DD
    cookies = session.get("cookies") or {}
    xsrf = session.get("xsrf_token")
    host_session = session.get("host_session_id")

    if not cookies or not xsrf or not host_session:
        log.error("Missing session info (cookies/xsrf/host_session) — cannot place first orders")
        return

    # Gather eligible symbols
    eligible = []
    for item in watchlist:
        symbol = item["symbol"]
        quantity = item["quantity"]

        # Check if already executed today
        if await has_first_order_executed(symbol, today):
            log.debug(f"{symbol} → already has first order today, skipping")
            continue

        # Check if symbol has IDs and pre_close price
        sec = await get_security(symbol)
        if not sec:
            log.debug(f"{symbol} → no security record in DB, skipping")
            continue

        if not sec.exchange_security_id or not sec.security_id:
            log.debug(f"{symbol} → missing IDs, skipping")
            continue

        if sec.last_pre_close is None:
            log.debug(f"{symbol} → missing last_pre_close price, skipping")
            continue
        
        # Calculate 2% chase price
        pre_close = float(sec.last_pre_close)
        chase_price = round_to_tick(pre_close * 1.02)
        
        eligible.append((symbol, chase_price, quantity))

    if not eligible:
        log.info("No eligible symbols for startup first orders")
        return

    log.info(f"🎯 Preparing {len(eligible)} concurrent first orders: {[e[0] for e in eligible]}")

    # ============================================================
    # STEP 1: Create one HTTP client per order
    # ============================================================
    clients = [httpx.AsyncClient(timeout=15.0, http2=True) for _ in eligible]
    log.info(f"✅ Created {len(clients)} HTTP clients")

    try:
        # ============================================================
        # STEP 2: Pre-warm connections (simple GET to check session)
        # ============================================================
        from config.settings import BASE_URL
        warmup_url = f"{BASE_URL}/tmsapi/dnaApi/exchange/session"
        
        warmup_headers = {
            "X-XSRF-TOKEN": xsrf,
            "host-session-id": host_session,
        }
        
        log.info("🔥 Pre-warming HTTP connections...")
        warmup_start = datetime.now()
        
        warmup_tasks = [
            client.get(warmup_url, headers=warmup_headers, cookies=cookies)
            for client in clients
        ]
        warmup_responses = await asyncio.gather(*warmup_tasks, return_exceptions=True)
        
        warmup_duration = (datetime.now() - warmup_start).total_seconds()
        successful_warmups = sum(1 for r in warmup_responses if not isinstance(r, Exception) and hasattr(r, 'status_code') and r.status_code == 200)
        log.info(f"✅ Pre-warmed {successful_warmups}/{len(clients)} connections in {warmup_duration:.3f}s")

        # ============================================================
        # STEP 3: Fire all orders SIMULTANEOUSLY
        # ============================================================
        await sleep_and_free_program_at(11, 0, 0)
        log.info("🚀 Firing all orders NOW!")
        order_start = datetime.now()
        
        # Create all order tasks
        order_tasks = []

        
        for i, (symbol, price, quantity) in enumerate(eligible):
            # Add small random delay: 0 to 50ms
            delay = i * 0.015 + (asyncio.get_event_loop().time() % 0.035)  # deterministic + random-ish
            async def delayed_place():
                await asyncio.sleep(delay)
                return await place_order_with_retries(
                    symbol=symbol,
                    price=price,
                    quantity=quantity,
                    cookies=cookies,
                    xsrf_token=xsrf,
                    host_session_id=host_session,
                    client=clients[i],
                )
            order_tasks.append((symbol, delayed_place()))

        results = await asyncio.gather(*[task for _, task in order_tasks], return_exceptions=True)



        order_duration = (datetime.now() - order_start).total_seconds()
        log.info(f"⚡ All orders completed in {order_duration:.3f}s")

        # ============================================================
        # STEP 4: Record results
        # ============================================================
        for (symbol, _), result in zip(order_tasks, results):
            try:
                if isinstance(result, Exception):
                    log.exception(f"{symbol} → order raised exception: {result}")
                    await record_first_order_execution(symbol, today, "failed", {"error": str(result)})
                else:
                    success, details = result
                    status = "sent" if success else "failed"
                    await record_first_order_execution(symbol, today, status, details)
                    log.info(f"{symbol} → first order recorded as {status}")
            except Exception as e:
                log.exception(f"{symbol} → error recording first order execution: {e}")

    finally:
        # ============================================================
        # STEP 5: Clean up all clients
        # ============================================================
        log.info("🧹 Closing all HTTP clients...")
        close_tasks = [client.aclose() for client in clients]
        await asyncio.gather(*close_tasks, return_exceptions=True)
        log.info("✅ All HTTP clients closed")

    log.info("🏁 Startup first orders completed")