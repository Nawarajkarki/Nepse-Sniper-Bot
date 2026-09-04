 
import asyncio
import os
from playwright_stealth import Stealth
from playwright.async_api import async_playwright, BrowserContext, Page
from config.settings import *

from core.session_manager import update_session
from utils.captcha_solver import captcha_solver

from utils.exception import *
from utils.discord_bot import send_private_message


print(F"tms base url == {TMS_BASE_URL}")

async def get_authenticated_session(keep_browser: bool = False) -> dict:
    """
    Returns:
        {
            "cookies": dict,
            "xsrf_token": str,
            "cookie_header": str
        }
    Browser is closed automatically after login.
    """
    
    host_session_id_container = [None]
    
    def extract_host_session_id(request):
        """Playwright request handler to check headers for the target ID."""
        nonlocal host_session_id_container
        
        # Only check requests targeting the TMS API and not external resources
        if "tmsapi" in request.url:
            headers = request.headers
            if 'host-session-id' in headers and host_session_id_container[0] is None:
                # Store the first one found and print a success message
                host_session_id_container[0] = headers['host-session-id']
                print(f"✅ Host Session ID Captured: {host_session_id_container[0]}")
                # Note: We don't remove the listener here; it is removed outside the handler.

    playwright = await async_playwright().start()     
    
    print(f"environment --> {ENVIRONMENT}")
    if ENVIRONMENT == "live":     
        browser = await playwright.chromium.launch(headless=True)
        # context = await browser.new_context()
        context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )    
        page = await context.new_page()
        stealth = Stealth()  # Create an instance (you can customize if needed)
        await stealth.apply_stealth_async(page)  # Apply to the page

    else:
        browser = await playwright.chromium.launch(headless=False)
        # context = await browser.new_context()
        context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )    
        page = await context.new_page()
    
    print("Opening TMS login page...")
    target_url = f"{TMS_BASE_URL}/login"
    print(f'target url = {target_url}')
    await page.goto(target_url)
        
        
    
    success = False
    for attempt in range(1, MAX_CAPTCHA_ATTEMPTS + 1):
        
        
        await page.wait_for_load_state("networkidle")

        await page.get_by_role("textbox", name="Client Code/ User Name").fill(CLIENT_CODE)
        await page.get_by_role("textbox", name="Password").fill(PASSWORD)
        
        # 1. Start listening for network requests *before* initiating login
        page.on("request", extract_host_session_id)
        
        
        
        # Wait for CAPTCHA image to load
        captcha_img_locator = page.locator("img[alt='Captcha']")  # or "img[alt='Captcha']"
        await captcha_img_locator.wait_for(state="visible", timeout=30000)

        # Solve CAPTCHA using the function above
        print(f"solving captcha")
        captcha_text = await captcha_solver(captcha_locator=captcha_img_locator, save_for_debug=True)
        print(f"Solved CAPTCHA: {captcha_text}")
        
        # Fill in the CAPTCHA field 
        await page.locator('id=captchaEnter').fill(captcha_text)
        
        # Click Login button
        await page.get_by_role("button", name="Login").click()

        await asyncio.sleep(2) 
        
        print(f"current page url == {page.url}")
        
        # Check if redirected to change password
        if "/tms/changepassword" in page.url:
            print("⚠️ Password expired!")
            await send_private_message("Password has expired. Please reset it.")
            # Close browser cleanup and raise custom exception or exit
            await browser.close()
            await playwright.stop()
            raise PasswordExpiredError("Password has expired. Please reset it.")
                
        if page.url.startswith(f"{TMS_BASE_URL}/tms/client/dashboard"):
            success = True
            break  # Exit retry loop immediately


        # === Error Checks ===
        try:
            wrong_captcha = await page.locator("span.toast-title:has-text('Wrong Captcha!')").is_visible(timeout=5000)
        except:
            wrong_captcha = False

        try:
            wrong_creds = await page.locator("span.toast-title:has-text('Please enter a correct username and password')").is_visible(timeout=5000)
        except:
            wrong_creds = False

        if wrong_creds:
            print("❌ Invalid username/password or wrong broker TMS URL.")
            # raise Exception("Invalid credentials or incorrect TMS URL. Stopping.")
            raise InvalidCredentialsError()

        if wrong_captcha:
            print("❌ Wrong CAPTCHA — retrying with fresh one...")
            continue  # Will trigger CAPTCHA reload above
        
        
        
        
        # Unknown error — retry anyway
        print("⚠️ Unknown login failure (no toast detected) — retrying...")
        # Optional: await page.screenshot(path=f"failed_attempt_{attempt}.png")
        await page.reload()

    else:
        # This runs if loop completes without break
        raise MaxCaptchaRetriesExceeded(MAX_CAPTCHA_ATTEMPTS)
    

    
    # print(f"⏳Waiting for captcha input")
    # print("Solve captcha manually and press Login → then come back here and press ENTER")
    # input(">>> Press ENTER after you are logged in and see the dashboard...")
    # print(f"✅ captcha solved")


    
    # Wait until dashboard loads
    await page.wait_for_url("**/tms/client/**", timeout=30_000)

    # Extract everything we need
    cookies = await context.cookies()
    cookies_dict = {c["name"]: c["value"] for c in cookies}
    xsrf = cookies_dict.get("XSRF-TOKEN", "")
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())

    

    print("Login successful — session captured")
    
    # Get the result from the container
    host_session_id = host_session_id_container[0] if host_session_id_container[0] is not None else "NOT_FOUND"
    print(f'cookie : {cookies_dict}, \n xsrf_token : {xsrf}, \n cookie_header: {cookie_header} \n host_session_id: {host_session_id}')
    
    
    result =  {
        
        "cookies": cookies_dict,
        "xsrf_token": xsrf,
        "cookie_header": cookie_header,
        "context": context,
        "browser": browser,
        "playwright": playwright,
        "host_session_id": host_session_id
    }
    result["original_cookies"] = cookies.copy()
    
    
    if not keep_browser:
        # Not keeping the browser: close + stop here.
        await browser.close()
        await playwright.stop()
        
    # Update global session snapshot
    await update_session(result)
    
    
    return result



# ────── ONLY FOR QUICK TESTING ──────
if __name__ == "__main__":
    import asyncio
    asyncio.run(get_authenticated_session())