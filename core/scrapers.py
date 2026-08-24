# core/scrapers.py
# Only used during one-time ID capture with Playwright
import re
import logging
from typing import Optional, Dict, Tuple
from playwright.async_api import Page

log = logging.getLogger("SCRAPER")

def parse_ltp(raw_text: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """
    Parse strings like:
      "123.45 (+2.12)", "123.45 (-1.23)" or "123.45"
    Returns (ltp, change)
    """
    if raw_text is None:
        return None, None
    raw = raw_text.strip().replace(",", "")
    match = re.match(r"^\s*([\d.]+)(?:\s*\(\s*([+-]?\d+(?:\.\d+)?)\s*\))?\s*$", raw)
    if match:
        try:
            ltp = float(match.group(1))
        except Exception:
            ltp = None
        change = None
        if match.group(2):
            try:
                change = float(match.group(2))
            except Exception:
                change = None
        return ltp, change
    try:
        return float(raw), None
    except Exception:
        return None, None


async def get_stock_values_from_order_page(page: Page) -> Dict[str, Optional[float]]:
    """
    Works on the memberclientorderentry page.
    Returns dict with ltp, pre_close, high, low, open values (floats or None).
    """
    async def get_value(label: str) -> Optional[str]:
        sel = f"div.order__form--prodtype:has(label:text-is('{label}'))"
        # Wait for element briefly — avoid hanging if not present
        try:
            el = await page.query_selector(sel)
            if not el:
                return None
            b = await el.query_selector("b")
            if b:
                text = await b.inner_text()
                return text.strip()
            # fallback: inner_text on the container
            text = await el.inner_text()
            return text.replace(label, "").strip()
        except Exception:
            log.debug("get_value: selector not found or parsing failed for label=%s", label, exc_info=True)
            return None

    ltp_raw = await get_value("LTP")
    ltp, _ = parse_ltp(ltp_raw)

    def try_float(v: Optional[str]) -> Optional[float]:
        if not v:
            return None
        try:
            return float(v.replace(",", "").strip())
        except Exception:
            return None

    pre_close_raw = await get_value("Pre Close")
    high_raw = await get_value("High")
    low_raw = await get_value("Low")
    open_raw = await get_value("Open")

    return {
        "ltp": ltp,
        "pre_close": try_float(pre_close_raw),
        "high": try_float(high_raw),
        "low": try_float(low_raw),
        "open": try_float(open_raw),
    }


