import os
import io
import time
import base64

import os
import base64
import requests
from PIL import Image
import io
from pathlib import Path


from config.settings import API_KEY, URL


async def captcha_solver(captcha_locator=None, screenshot_bytes=None, save_for_debug=True):
    """
    Solves CAPTCHA using CapMonster (or 2Captcha-compatible) API.
    """
    create_endpoint = "/createTask"
    create_url = URL + create_endpoint
    print("inside captcha solver")
    # Get screenshot bytes
    if screenshot_bytes is None:
        if captcha_locator is None:
            raise ValueError("Either captcha_locator or screenshot_bytes must be provided")
        screenshot_bytes = await captcha_locator.screenshot(type="png")

    # Saves image locally for debugging
    if save_for_debug:
        save_dir = Path("captcha_img")
        save_dir.mkdir(exist_ok=True)
        save_path = save_dir / "captcha.png"
        save_path.write_bytes(screenshot_bytes)
        print(f"Captcha image saved to: {save_path.resolve()}")

    captcha_image_data = base64.b64encode(screenshot_bytes).decode('utf-8')

    payload = {
        "clientKey": API_KEY,
        "task": {
            "type": "ImageToTextTask",
            "body": captcha_image_data,
            "phrase": False,
            "caseSensitive": False,
            "numeric": 0,        # 0 = any, 1 = only numbers, 2 = only letters
            "math": False,
            "minLength": 5,
            "maxLength": 6,
        }
    }

    # Send task creation request
    response = requests.post(create_url, json=payload)
    print(response.text)
    print(response.status_code)
    response.raise_for_status()  # Will raise error if not 200

    data = response.json()
    print("CreateTask response:", response.text)

    if data.get("errorId") != 0:
        raise Exception(f"CapMonster Error: {data.get('errorDescription')}")

    task_id = data.get("taskId")
    if not task_id:
        raise Exception("No taskId returned from CapMonster")

    print(f"CapMonster task created: {task_id}")

    # Poll for result
    captcha_text = await get_task_result(task_id)
    return captcha_text


async def get_task_result(task_id):
    """
    Polls CapMonster /getTaskResult until CAPTCHA is solved.
    Made async-friendly with asyncio.sleep (but still uses sync requests – safe in Playwright).
    """
    import asyncio 

    result_endpoint = "/getTaskResult"
    result_url = URL + result_endpoint

    payload = {
        "clientKey": API_KEY,
        "taskId": task_id
    }

    while True:
        response = requests.post(result_url, json=payload)
        resp_json = response.json()
        print("getTaskResult response:", response.text)

        if resp_json.get("errorId") != 0:
            raise Exception(f"CapMonster Polling Error: {resp_json.get('errorDescription')}")

        status = resp_json.get("status")

        if status == "ready":
            text = resp_json.get("solution", {}).get("text", "")
            # Common fix for NEPSE CAPTCHA: 'o' → '0', sometimes 'O' or 'l' → '1', etc.
            cleaned_text = text.replace('o', '0').replace('O', '0').strip()
            print(f"CAPTCHA solved: {cleaned_text}")
            return cleaned_text

        elif status == "processing":
            print("Still processing... waiting 3 seconds")
            await asyncio.sleep(3)
        else:
            await asyncio.sleep(3)