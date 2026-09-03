import pytz
import sys
import argparse
import asyncio
import logging
import random

import orjson
from pathlib import Path

from datetime import datetime


from core.database import (
    init_db,
    save_trade_config,
    get_security,
    save_or_update_security,
    get_all_trade_config_symbols,
    set_trade_config_enabled
)
from config.symbols import WATCHLIST
from core.session import get_authenticated_session
from core.id_resolver import resolve_missing_ids
from core.websocket_client import start_all_websocket_clients
from core.first_order import run_startup_first_orders
from core.session_manager import start_token_keeper
from utils.timing import sleep_and_free_program_at, check_time_before_3pm, stop_at_3pm_periodically
from utils.exception import *
from utils.scrape_pre_close import update_only_enabled_symbols_preclose



LOG_FORMAT = '%(asctime)s.%(msecs)03d --> %(levelname)s:%(name)s: %(message)s'
TIME_FORMAT = '%H:%M:%S'

normal_formatter = logging.Formatter(LOG_FORMAT, datefmt=TIME_FORMAT)
header_formatter = logging.Formatter('%(message)s')

file_handler = logging.FileHandler("logs/app.log", encoding="utf-8")
file_handler.setFormatter(normal_formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(normal_formatter)

header_handler = logging.FileHandler("logs/app.log", encoding="utf-8")
header_handler.setFormatter(header_formatter)



log = logging.getLogger("MAIN")
log.setLevel(logging.INFO)
log.addHandler(file_handler)
log.addHandler(console_handler)

log_header = logging.getLogger("LOG_HEADER")
log_header.setLevel(logging.INFO)
log_header.addHandler(header_handler)
log_header.propagate = False







# ######   Load the Buy Payload Once During Startup & use same thing for all 

TEMPLATE_PATH = Path("config/buy_payload_template.json")

if not TEMPLATE_PATH.exists():
    raise FileNotFoundError("config/buy_payload_template.json missing — capture it once from browser!")


with open(TEMPLATE_PATH, "rb") as f:               # ← note: binary mode is preferred for orjson
    BUY_PAYLOAD_TEMPLATE = orjson.loads(f.read())





async def seed_trade_config() -> None:
    """Ensure trade_config has entries for all watchlist items."""
    for item in WATCHLIST:
        await save_trade_config(item["symbol"], item["quantity"])
    log.info("Trade config seeded from WATCHLIST.")


async def prune_removed_watchlist_symbols() -> int:
    """
    Disable any trade_config entries that are currently enabled but not in WATCHLIST.
    Returns number of symbols disabled.
    """
    try:
        enabled_symbols = set(await get_all_trade_config_symbols())
    except Exception:
        # fallback: try older helper if needed
        enabled_symbols = set()
    watch_symbols = {item["symbol"] for item in WATCHLIST}
    to_disable = enabled_symbols - watch_symbols
    disabled_count = 0
    for sym in to_disable:
        await set_trade_config_enabled(sym, False)
        log.info(f"Pruned (disabled) trade_config for symbol not in WATCHLIST: {sym}")
        disabled_count += 1
    return disabled_count

    
async def needs_id_resolution() -> bool:
    """Check DB for symbols missing IDs; returns True if any missing."""
    for item in WATCHLIST:
        sym = item["symbol"]
        sec = await get_security(sym)
        if not sec or not sec.security_id or not sec.exchange_security_id:
            log.info(f"{sym} missing IDs → will resolve via browser.")
            return True
    return False


async def seed_fake_securities() -> None:
    """For offline/dry-run testing: seed fake IDs so websockets and order flows can be exercised."""
    for item in WATCHLIST:
        symbol = item["symbol"]
        sec = await get_security(symbol)
        if sec and sec.exchange_security_id and sec.security_id:
            continue
        # deterministic-ish fake values for easier debugging
        exchange_id = 10000 + hash(symbol) % 10000
        security_id = 200000 + hash(symbol) % 10000
        await save_or_update_security(symbol, exchange_id, security_id, pre_close=10.0)
        log.info(f"[DRYRUN] Seeded {symbol} with exchange_id={exchange_id}, security_id={security_id}")




async def print_log_date_header():

    NEPAL_TZ = pytz.timezone("Asia/Kathmandu")

    
    today = datetime.now(NEPAL_TZ).strftime("%Y-%m-%d (%A)")


    
    width = 60
    log_header.info("\n" + "┌" + "─" * (width - 2) + "┐")
    log_header.info(f"│  📅  {today}".ljust(width - 1) + "│")
    log_header.info("└" + "─" * (width - 2) + "┘\n")





    
    

async def main(
    resolve_ids: bool = True, 
    wait_until_open: bool = True, 
    test_run : bool = False
    ) -> None:
    
    
    await print_log_date_header()
    await init_db()
    await seed_trade_config()

    # Remove disabled symbols 
    removed = await prune_removed_watchlist_symbols()
    if removed:
        log.info(f"Disabled {removed} symbols removed from WATCHLIST")
            

    need_resolve = resolve_ids and await needs_id_resolution()

    
    update_pre_close_prices = asyncio.create_task(update_only_enabled_symbols_preclose())
    
    if not test_run:
        await check_time_before_3pm()
    
    # Authenticate & optionally keep browser for ID resolution
    try:
        session = await get_authenticated_session(keep_browser=need_resolve)
    except InvalidCredentialsError:
        log.error("❌❌💔❌❌ Program aborted due to invalid credentials.")
        sys.exit(1)
    except MaxCaptchaRetriesExceeded:
        log.error("💔💔💔💔💔 Program aborted due to exceeding CAPTCHA retry limit.")
        sys.exit(1)
    except Exception as e:
        log.error(f"❌❌❌ Authentication failed: {e}")
        sys.exit(1)
    
    
    # ========== Start Session Manager IMMEDIATELY ==========
    log.info("Starting session manager task (background)...")
    keeper_task = asyncio.create_task(start_token_keeper(session))

    
    
    await update_pre_close_prices 
    
    #  wait until 11:00 AM Nepal Time
    if wait_until_open:
        await sleep_and_free_program_at(10, 59, 45)
    
    
    asyncio.create_task(stop_at_3pm_periodically())
    
    # ========== Place First Order at Sharp 11:00  ==========
    log.info("Running startup first orders...")
    # ensure the scraper has updated all symbol's prices.
    try:
        await run_startup_first_orders(session)
    except Exception as e:
        log.exception(f"Startup first orders failed: {e}")
        
    # If IDs missing, run the resolver (requires context + browser alive)
    if need_resolve:
        # Stop the old keeper first (session is about to die/change)
        if keeper_task:
            keeper_task.cancel()
            try:
                await keeper_task
            except asyncio.CancelledError:
                pass
            log.info("Stopped initial token keeper for ID resolution.")

        context = session.get("context")
        if context is None:
            log.error("ID resolution requested but no browser context available. Aborting.")
        else:
            await resolve_missing_ids(context)
            # Close the browser afterwards (session returns `browser` when keep_browser=True)
            browser = session.get("browser")
            playwright = session.get("playwright")
            if browser:
                await browser.close()
                log.info("Playwright browser closed after ID resolution.")
            if playwright:
                # ensure playwright stops cleanly
                try:
                    await playwright.stop()
                except Exception:
                    log.debug("failed to stop playwright cleanly", exc_info=True)
                    

    # Launch websockets using the returned session cookies and tokens
    log.info("Starting websocket clients...")
    try:
        await start_all_websocket_clients(session)
    except asyncio.CancelledError:
        log.info("Websocket clients cancelled, shutting down.")
    except Exception as e:
        log.exception(f"Websocket clients crashed: {e}")
    
    finally:
        if keeper_task:
            keeper_task.cancel()
            try:
                await keeper_task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NEPSE Sniper — main runner")
    parser.add_argument("--no-resolve", action="store_true", help="Skip the Playwright ID resolution step")
    parser.add_argument("--no-wait", action="store_true", help="Don't wait until 11:00 AM Nepal time; start immediately")
    args = parser.parse_args()

    resolve = not args.no_resolve
    wait = not args.no_wait

    asyncio.run(main(resolve_ids=resolve, wait_until_open=wait))