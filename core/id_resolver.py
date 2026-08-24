 
# core/id_resolver.py
import json
import asyncio
from pathlib import Path
import sys
import logging

from urllib.parse import urlparse

from playwright.async_api import Page, Request, BrowserContext
from config.symbols import WATCHLIST
from core.database import save_or_update_security, get_security
from core.scrapers import get_stock_values_from_order_page

from config.settings import TMS_BASE_URL
from typing import Optional, Tuple


sys.path.append(str(Path(__file__).resolve().parent.parent))
log = logging.getLogger("ID_RESOLVER")






REQUEST_TIMEOUT = 8.0

def _get_req_post_data_sync_compat(req: Request):
    try:
        maybe = req.post_data
        if callable(maybe):
            maybe = maybe()
        return maybe
    except Exception:
        try:
            return req.post_data
        except Exception:
            return None

async def _read_request_body(req: Request) -> str | None:
    raw = _get_req_post_data_sync_compat(req)
    if asyncio.iscoroutine(raw):
        try:
            return await raw
        except Exception:
            return None
    return raw




def parse_order_payload(payload: dict) -> Tuple[Optional[int], Optional[int]]:
    """
    Extracts (exchange_security_id, security_id) from an order POST payload.
    Returns (None, None) if not present or parse error.
    """
    try:
        order_book = payload.get("orderBook") or {}
        security = order_book.get("security") or {}
        exch = security.get("exchangeSecurityId")
        sec_id = security.get("id")
        exchange_id = int(exch) if exch is not None else None
        security_id = int(sec_id) if sec_id is not None else None
        return exchange_id, security_id
    except Exception:
        return None, None

        
        


async def resolve_missing_ids(context: BrowserContext, dry_run: bool = False) -> None:
    """
    Must be called AFTER successful login (context already authenticated).
    For each symbol in WATCHLIST:
      - Opens order entry page
      - Triggers a valid BUY order (frontend validation must allow it)
      - Waits for the POST to /orderApi/order/ → extracts both IDs
      - Saves to DB + current pre_close
    If dry_run=True, just seed fake IDs to the DB for offline testing.
    """
    if dry_run:
        import random
        for item in WATCHLIST:
            symbol = item["symbol"]
            sec = await get_security(symbol)
            if sec and sec.exchange_security_id and sec.security_id:
                continue
            # assign fake ids (stable-ish)
            await save_or_update_security(
                symbol=symbol,
                exchange_id=100000 + random.randint(0, 999),
                sec_id=200000 + random.randint(0, 999),
                pre_close=10.0,
            )
            print(f"[DRYRUN] Seeded fake security for {symbol}")
        return

    page = await context.new_page()

    for item in WATCHLIST:
        symbol = item["symbol"]
        quantity = item["quantity"]

        print(f"\nResolving IDs for {symbol}...")

        # Check if we already have both IDs
        sec = await get_security(symbol)
        if sec and sec.exchange_security_id and sec.security_id:
            print(f"Already resolved → exchange_id={sec.exchange_security_id}, security_id={sec.security_id}")
            continue

        # Open order page
        target_url = f"{TMS_BASE_URL}/tms/me/memberclientorderentry?symbol={symbol}&transaction=Buy"
        await page.goto(target_url)

        await page.wait_for_load_state("networkidle")

        vals = await get_stock_values_from_order_page(page)
        pre_close = vals.get("pre_close")
        high = vals.get("high")
        ltp = vals.get("ltp")

        # Choose a valid price that passes frontend validations and triggers a real POST.
        if high:
            dummy_price = float(high)
        elif ltp:
            dummy_price = float(ltp)
        elif pre_close:
            dummy_price = float(pre_close) * 1.02
        else:
            dummy_price = 10.0 + quantity  # fallback
        
        # Fill inputs
        await page.locator("input[formcontrolname='quantity']").fill(str(max(10, int(quantity))))
        await page.locator("input[formcontrolname='price']").fill(str(dummy_price))

        # Ensure BUY button is ready
        buy_btn = page.get_by_role("button", name="BUY", exact=True)
        await buy_btn.wait_for(state="visible", timeout=10000)
        if not await buy_btn.is_enabled():
            print(f"[{symbol}] BUY button disabled — validation failed")
            continue

        # CORRECT: Click inside the expect_request block
        try:
            async with page.expect_request(
                lambda r: "/tmsapi/orderApi/order/" in r.url and r.method == "POST",
                timeout=10000
            ) as request_info:
                await buy_btn.click(force=True)
                # Fallback: press Enter (some TMS builds need it)
                await page.locator("input[formcontrolname='price']").press("Enter")

            req = await request_info.value
            body = req.post_data
            if not body:
                print(f"[{symbol}] Captured request but no body")
                continue

            captured_payload = json.loads(body)

        except TimeoutError:
            print(f"[{symbol}] TIMEOUT: No POST captured — order likely blocked by validation")
            continue
        except Exception as e:
            print(f"[{symbol}] Unexpected error: {e}")
            continue

        # Extract IDs
        exchange_id, security_id = parse_order_payload(captured_payload)
        if not (exchange_id and security_id):
            print(f"[{symbol}] Failed to extract IDs from payload")
            continue

        await save_or_update_security(
            symbol=symbol,
            exchange_id=exchange_id,
            sec_id=security_id,
            pre_close=pre_close
        )
        print(f"SUCCESS → {symbol} | exchange_id={exchange_id} | security_id={security_id} | pre_close={pre_close}")
        
        
        await page.wait_for_timeout(400)

    await page.close()
    print("\nAll symbols resolved — browser can now be closed forever!")
    
    


    
    
    
  

# ────── TEST BLOCK (run only after login) ──────
if __name__ == "__main__":
    from core.session import get_authenticated_session
    async def test():
        session = await get_authenticated_session()
        context = session["context"]  # we'll modify session.py to return context too
        await resolve_missing_ids(context)
    asyncio.run(test())