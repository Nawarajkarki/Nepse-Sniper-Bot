import time
import httpx
import logging
import json
import asyncio
from pathlib import Path
from decimal import Decimal
from config.settings import *
from core.session_manager import get_session_snapshot, _api_refresh_token

from config.payloads import create_buy_payload
# from config.templates import create_buy_payload


log = logging.getLogger("ORDER")



async def place_order( 
        symbol: str, 
        price: float, 
        quantity: int, 
        cookies: dict = None, 
        xsrf_token: str = None, 
        host_session_id: str = None, 
        client: 'httpx.AsyncClient' = None
    ):
    from core.database import get_security


    sec = await get_security(symbol)
    if not sec or not sec.security_id or not sec.exchange_security_id:
        log.error(f"{symbol} → missing IDs")
        return False


    # Deep copy template
    
    payload = create_buy_payload(
        price=price,
        quantity=quantity,
        security_id=sec.security_id,
        exchange_security_id=sec.exchange_security_id
    )


    created_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=12.0, http2=True)
        created_client = True
        
            
    for i in range(3):
        
        
        session = await get_session_snapshot()

        
        cookies = session.get("cookies")
        xsrf_token = session.get("xsrf_token")
        host_session_id = session.get("host_session_id")
        

        headers = {
            "Content-Type": "application/json",
            "X-XSRF-TOKEN": xsrf_token,
            "host-session-id": host_session_id,
            "Request-Owner": REQUEST_OWNER,
            "MemberCode": MEMBER_CODE,
            "Origin": TMS_BASE_URL,
            "Referer": f"{TMS_BASE_URL}/tms/me/memberclientorderentry",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        
        try:
            # log.info(f"Placing Order {symbol} X {quantity} @ {price}")
            r = await client.post(
                ORDER_API_URL,
                json=payload,
                headers=headers,
                cookies=cookies           # ← full cookie jar (not just string)
            )

            if r.status_code == 200:
                result = r.json()
                order_id = result.get("orderId", "UNKNOWN")
                log.info(f"✅ ORDER SUCCESS {symbol} × {quantity} @ {price} | Order ID: {order_id}")
                return True
            elif r.status_code == 401:
                log.warning(f"ORDER 401 UNAUTHORIZED → refreshing session and retrying... ({i+1}/3)")
                await _api_refresh_token(session_data=session, client=client)
                continue
            else:
                log.error(f"💔 FAILED {symbol} | {r.status_code} | {r.text[:300]}")
                return False

        except Exception as e:
            log.exception(f"💔 EXCEPTION {symbol}: {e}")
            return False
        
        finally:
            if created_client:
                try:
                    await client.aclose()
                except Exception:
                    pass

            
