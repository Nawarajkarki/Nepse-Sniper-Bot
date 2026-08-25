import sys

import asyncio

import datetime
import time
import pytz

NEPAL_TZ = pytz.timezone("Asia/Kathmandu")


async def sleep_and_free_program_at(hours = 11, minutes = 0, seconds = 0) -> None:
    """ 
    Blocks execution until exactly 11:00:00 AM Nepal Time today.
    If it's already past 11:00 AM, returns immediately.
    Prints clear status messages.
    """
    now = datetime.datetime.now(NEPAL_TZ)
    today_11_am = NEPAL_TZ.localize(
        datetime.datetime.combine(now.date(), datetime.time(hours, minutes, seconds))
    )

    if now >= today_11_am:
        print(f"[{now.strftime('%H:%M:%S')}] Already 11:00 AM or later → continuing immediately")
        return

    sleep_seconds = (today_11_am - now).total_seconds()
    hours = sleep_seconds // 3600
    minutes = (sleep_seconds % 3600) // 60

    print(f"[{now.strftime('%H:%M:%S')}] Sleeping {sleep_seconds:.0f}s "
          f"({hours:.0f}h {minutes:.0f}min) until 11:00:00 AM Nepal time...")

    await asyncio.sleep(sleep_seconds)
    print(f"[{datetime.datetime.now(NEPAL_TZ).strftime('%H:%M:%S')}] 11:00:00 AM reached — starting sniper!")



        
        
async def check_time_before_3pm() -> None:
    """ 
    Stop the Bot if it after 3:00:00 PM Nepal Time today.
    Don't proceed forward if it's past 3
    """
    now = datetime.datetime.now(NEPAL_TZ)
    today_3_pm = NEPAL_TZ.localize(
        datetime.datetime.combine(now.date(), datetime.time(15, 0, 0))
    )

    if now >= today_3_pm:
        print(f" ⏰ It's past 3:00 PM ({now.strftime('%H:%M:%S')}). Bot will not run today.")
        sys.exit(0)

async def stop_at_3pm_periodically() -> None:
    """ 
    Stop the Bot if it after 3:00:00 PM Nepal Time today.
    Don't proceed forward if it's past 3
    """
    now = datetime.datetime.now(NEPAL_TZ)
    today_3_pm = NEPAL_TZ.localize(
        datetime.datetime.combine(now.date(), datetime.time(15, 0, 0))
    )

    if now >= today_3_pm:
        print(f"⏰ 3:00 PM reached ({now.strftime('%H:%M:%S')}). Stopping bot.")
        sys.exit(0)






async def main():
    await sleep_and_free_program_at(11, 0, 0)
    
    
if __name__ == "__main__":
    asyncio.run(main())
    
    