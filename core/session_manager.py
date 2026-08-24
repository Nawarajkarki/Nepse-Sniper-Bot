
import logging
import datetime
import pytz
import asyncio
import httpx


from config.settings import MEMBER_CODE, REQUEST_OWNER


import logging
import logging.handlers

# --- Logger Setup ---
log = logging.getLogger("SESSION_MANAGER")
log.setLevel(logging.INFO) 

formatter = logging.Formatter(
    '%(asctime)s --> %(message)s',
    datefmt='%H:%M:%S'
)

# File Handler: Writes logs to a file (session_manager.log)
file_handler = logging.handlers.RotatingFileHandler(
    'logs/session_manager.log',
    maxBytes=1048576, # 1MB max file size
    backupCount=5     # Keep 5 backup logs
)
file_handler.setFormatter(formatter)
log.addHandler(file_handler)

# Console Handler : Writes logs to the terminal
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
log.addHandler(console_handler)
# --------------------




# Global session snapshot
SESSION_SNAPSHOT = {}
SESSION_LOCK = asyncio.Lock()

async def update_session(session_data: dict):
    """
    Update session atomically - safe for lock-free reads.
    """
    # Build NEW dict completely BEFORE replacing
    new_snapshot = {
        "cookies": session_data.get("cookies"),
        "xsrf_token": session_data.get("xsrf_token"),
        "cookie_header": session_data.get("cookie_header"),
        "host_session_id": session_data.get("host_session_id"),
        "original_cookies": session_data.get("original_cookies")
    }
    
    # ATOMIC replacement
    global SESSION_SNAPSHOT
    SESSION_SNAPSHOT = new_snapshot  # ← This is atomic in Python!


async def get_session_snapshot() -> dict:
    """
    Read session without lock - safe because updates are atomic.
    """
    # see old or new snapshot, never half-updated
    return SESSION_SNAPSHOT.copy()





NEPAL_TZ = pytz.timezone("Asia/Kathmandu")

# Use global lock for safety
REFRESH_LOCK = asyncio.Lock()

SESSION_CHECK = "/tmsapi/dnaApi/exchange/sessionCheck"
SESSION       = "/tmsapi/dnaApi/exchange/session"
REFRESH       = "/tmsapi/authApi/authenticate/refresh"
BASE_URL      = "https://tms49.nepsetms.com.np"




# --- GLOBAL HTTP CLIENT ---
# Initialized to None and created later for efficiency
GLOBAL_CLIENT: httpx.AsyncClient = None

# --- Helper Functions for HTTP Calls ---

async def _api_session_check(client: httpx.AsyncClient, session_data: dict) -> int:
    """Hits the session check endpoint and returns status code."""
    url = f"{BASE_URL}{SESSION}"
    
    headers = {
        "X-XSRF-TOKEN": session_data.get("xsrf_token"),
        "host-session-id": session_data.get('host_session_id'),
        "Request-Owner": REQUEST_OWNER,
        "MemberCode": MEMBER_CODE,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    try:
        resp = await client.get(url, headers=headers, cookies=session_data.get("cookies"))
        log.info(f"Session Check status: {resp.status_code}")
        return resp.status_code
    except Exception as e:
        log.exception(f"API Session check FAILED: {e}")
        return 0 # Return 0 for connection errors/exceptions


async def _api_refresh_token( session_data: dict, client: httpx.AsyncClient=None) -> bool:
    """Attempts to refresh token and updates global session on success."""
    url = f"{BASE_URL}{REFRESH}"
    
    client_created = False
    if client is None:
        client = httpx.AsyncClient(timeout=10.0, http2=True)
        client_created = True
        
        
    headers = {
        "X-XSRF-TOKEN": session_data.get("xsrf_token"),
        "host-session-id": session_data.get('host_session_id'),
        "Request-Owner": REQUEST_OWNER,
        "MemberCode": MEMBER_CODE,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/tms/me/memberclientorderentry",
    }
    
    try:
        refresh_resp = await client.post(url, headers=headers, cookies=session_data.get("cookies"))
        
        if refresh_resp.status_code == 200:
            # --- Extraction Logic ---
            new_cookies = {c.name: c.value for c in refresh_resp.cookies.jar}
            new_xsrf = new_cookies.get("XSRF-TOKEN", session_data.get("xsrf_token"))
            cookie_header = "; ".join(f"{k}={v}" for k, v in new_cookies.items())
            host_session_id = new_cookies.get("host-session-id", session_data.get("host_session_id"))

            new_snapshot = {
                "cookies": new_cookies,
                "xsrf_token": new_xsrf,
                "cookie_header": cookie_header,
                "host_session_id": host_session_id,
                "original_cookies": new_cookies.copy()
            }

            await update_session(new_snapshot)
            log.info("Session successfully refreshed and global snapshot updated.")
            return True
        else:
            log.error(f"Refresh FAILED: Status {refresh_resp.status_code}. Response: {refresh_resp.text[:100]}...")
            return False

    except Exception as e:
        log.exception(f"API Token Refresh FAILED with exception: {e}")
        return False
    
    finally:
        if client_created:
            try:
                await client.aclose()
            except Exception:
                pass


async def start_token_keeper(initial_session: dict, hrs=10, minute=59, second=40):
    """
    Background task: refresh session after 10:59:40 and keeps it alive.
    """
    global GLOBAL_CLIENT # Important: declare intent to use global variable

    # Long-Lived Client Initialization ---
    if GLOBAL_CLIENT is None:
        GLOBAL_CLIENT = httpx.AsyncClient(timeout=10.0, http2=True)
        log.info("Long-lived HTTP client initialized.")

    now = datetime.datetime.now(NEPAL_TZ)
    target_time = NEPAL_TZ.localize(
        datetime.datetime.combine(now.date(), datetime.time(10, 59, 40))
    )
    
    if now < target_time:
        sleep_seconds = (target_time - now).total_seconds()
        log.info(f"Bot started early. Sleeping for {int(sleep_seconds)} seconds until 10:59:40 NPT.")
        await asyncio.sleep(sleep_seconds)
        log.info("Reached 10:59:40 NPT. Starting session check/refresh loop.")

    while True:
        async with REFRESH_LOCK:
            session_snapshot = await get_session_snapshot()
            
            status = await _api_session_check(GLOBAL_CLIENT, session_snapshot)

            if status == 0 or status == 401:
                log.info("Session check failed (expired or connection error). Attempting refresh.")
                refresh_success = await _api_refresh_token(session_snapshot, GLOBAL_CLIENT)
                
                if refresh_success:
                    # If successful, we wait less time to re-check the validity after the critical refresh
                    await asyncio.sleep(5) 
                else:
                    continue
            else:
                # Session is fine, just wait for the next periodic check
                await asyncio.sleep(55.5)


# --- Application Shutdown Hook (Requires a mechanism to call this) ---
async def shutdown_session_manager():
    """Call this function when the application is closing."""
    if GLOBAL_CLIENT:
        await GLOBAL_CLIENT.aclose()
        log.info("Long-lived HTTP client closed gracefully.")