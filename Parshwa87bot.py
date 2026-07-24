import os
import datetime
import requests
import pytz

# ==================== CONFIGURATION ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DHAN_CLIENT_ID = os.getenv("DHAN_CLIENT_ID", "1112617852")
DHAN_ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN")

def send_telegram_message(message):
    """Telegram Alert Function"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def debug_dhan_api():
    """Dhan API Raw Response Inspector"""
    headers = {
        "access-token": DHAN_ACCESS_TOKEN,
        "client-id": DHAN_CLIENT_ID,
        "Content-Type": "application/json"
    }
    
    # 1. Check Expiry List Raw
    exp_url = "https://api.dhan.co/v2/optionchain/expirylist"
    exp_payload = {"UnderlyingScrip": 13, "UnderlyingSeg": "NSE_INDEX"}
    exp_res = requests.post(exp_url, json=exp_payload, headers=headers, timeout=10)
    
    # 2. Check Option Chain Raw
    oc_url = "https://api.dhan.co/v2/optionchain"
    oc_payload = {
        "UnderlyingScrip": 13,
        "UnderlyingSeg": "NSE_INDEX",
        "Expiry": "2026-07-30"  # Expiry date string
    }
    oc_res = requests.post(oc_url, json=oc_payload, headers=headers, timeout=10)
    
    msg = f"🔍 **DHAN API RAW DEBUG REPORT** 🔍\n\n"
    msg += f"• **Expiry Status Code:** `{exp_res.status_code}`\n"
    msg += f"• **Expiry Response Snippet:** `{exp_res.text[:150]}`\n\n"
    msg += f"• **OptionChain Status Code:** `{oc_res.status_code}`\n"
    msg += f"• **OptionChain Response Snippet:** `{oc_res.text[:250]}`"
    
    return msg

if __name__ == "__main__":
    report = debug_dhan_api()
    send_telegram_message(report)
