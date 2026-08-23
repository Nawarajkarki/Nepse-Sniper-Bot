 
# config/settings.py
from dotenv import load_dotenv
import os

load_dotenv()  # Load .env from project root

# NEPSE Specifics

DAILY_CIRCUIT = 1.15


# Settings

MAX_CAPTCHA_ATTEMPTS = 5

ENVIRONMENT = os.getenv("ENVIRONMENT", "live")


# Required

NAME = os.getenv("NAME")
ID = os.getenv("ID")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")
NOT_UNIQUE_CLIENT_CODE = os.getenv("NOT_UNIQUE_CLIENT_CODE")
CLIENT_CODE = os.getenv("CLIENT_CODE")
PASSWORD = os.getenv("PASSWORD")


# CapMonster
API_KEY = os.getenv("API_KEY")
URL = os.getenv("URL")


# Static from HAR
CLIENT_ID = int(os.getenv("CLIENT_ID", "0"))
REQUEST_OWNER = os.getenv("REQUEST_OWNER")
MEMBER_CODE = os.getenv("MEMBER_CODE")

# URLs
BASE_URL = os.getenv("BASE_URL")
WS_URL = f"wss://tms49.nepsetms.com.np/tmsapi/exskt/websocket?memberCode={MEMBER_CODE}"
ORDER_API_URL = "https://tms49.nepsetms.com.np/tmsapi/orderApi/order/"



# Safety check
if not CLIENT_CODE or not PASSWORD:
    raise RuntimeError("Set CLIENT_CODE and PASSWORD in .env file!")