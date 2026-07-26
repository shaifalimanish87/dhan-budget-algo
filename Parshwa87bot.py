import os
import datetime
import requests
import pytz

# ==================== CONFIGURATION ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY")
UPSTOX_API_SECRET = os.getenv("UPSTOX_API_SECRET")
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")  # If static token generated


# ==================== HELPER FUNCTIONS ====================

def format_lakhs(number):
    """Numbers ko Lakhs (Lakh) me format karta hai"""
    if number is None:
        return "Data Unavailable ⚠️"
    if number == 0:
        return "0.00 Lakh"
    lakh_value = number / 100000
    sign = "+" if lakh_value > 0 else ""
    if lakh_value < 0:
        return f"-{abs(lakh_value):.2f} Lakh"
    else:
        return f"{sign}{lakh_value:.2f} Lakh"


def send_telegram_message(message):
    """Telegram Alert Function"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram Secrets Missing!")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        print(f"Telegram API Status Code: {r.status_code}")
    except Exception as e:
        print(f"Telegram Post Error: {e}")


# ==================== THEORY 1: MARKET SENTIMENT ====================

def get_market_news_and_macro_sentiment():
    """Theory 1: Global Cues & FII Trend Parsing"""
    sentiment_score = 0
    cues_summary = []

    # Basic Global Sentiment Mock / Lightweight API
    try:
        url = "https://www.moneycontrol.com/stocks/marketstats/fii_dii_activity/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            content = res.text.lower()
            if "net buy" in content:
                sentiment_score += 1
                fii_status = "Net Buyers 🟢"
            elif "net sell" in content:
                sentiment_score -= 1
                fii_status = "Net Sellers 🔴"
            else:
                fii_status = "Neutral / Balanced 🟡"
        else:
            fii_status = "Data Unavailable ⚠️"
    except Exception as e:
        print(f"⚠️ FII Scraping Error: {e}")
        fii_status = "Data Unavailable ⚠️"

    if sentiment_score >= 1:
        sentiment = "🟢 **BULLISH (Market Trend Positive)**"
    elif sentiment_score <= -1:
        sentiment = "🔴 **BEARISH (Market Trend Negative)**"
    else:
        sentiment = "🟡 **NEUTRAL / MIXED (Cues Sideways)**"

    return sentiment, cues_summary, fii_status


# ==================== THEORY 2: UPSTOX REALTIME OI ENGINE ====================

def get_upstox_option_chain():
    """Upstox Market Data V2 - Nifty Option Chain Fetcher"""
    if not UPSTOX_ACCESS_TOKEN:
        print("⚠️ UPSTOX_ACCESS_TOKEN Missing. Trying Public Instrument Quote...")

    # Upstox Instrument Key for Nifty 50 Index
    instrument_key = "NSE_INDEX|Nifty 50"
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {UPSTOX_ACCESS_TOKEN}' if UPSTOX_ACCESS_TOKEN else ''
    }

    try:
        # Step 1: Get Nifty Live Spot Price
        quote_url = f"https://api.upstox.com/v2/market-quote/quotes?instrument_key={instrument_key}"
        res = requests.get(quote_url, headers=headers, timeout=8)
        
        spot_price = 0.0
        if res.status_code == 200:
            data = res.json().get("data", {})
            spot_price = float(data.get("NSE_INDEX:Nifty 50", {}).get("last_price", 0.0))
            print(f"✅ Upstox Live Nifty Spot Price: {spot_price}")

        if spot_price == 0.0:
            print("❌ Failed to fetch live spot price from Upstox.")
            return None

        strike_step = 50
        atm_strike = int(round(spot_price / strike_step) * strike_step)

        itm_ce_strikes = [atm_strike, atm_strike - strike_step, atm_strike - (2 * strike_step)]
        itm_pe_strikes = [atm_strike, atm_strike + strike_step, atm_strike + (2 * strike_step)]

        # Step 2: Fetch Option Chain Data
        # Note: Upstox option chain endpoint requires expiry date format (YYYY-MM-DD)
        # Standard fallback mechanism if specific expiry chain call is made
        chain_url = f"https://api.upstox.com/v2/option/chain?instrument_key={instrument_key}"
        chain_res = requests.get(chain_url, headers=headers, timeout=8)

        ce_total_oi = 0
        pe_total_oi = 0

        if chain_res.status_code == 200:
            chain_data = chain_res.json().get("data", [])
            for row in chain_data:
                stk = int(round(float(row.get("strike_price", 0))))
                
                # Check Call Option (CE)
                if stk in itm_ce_strikes and "call_options" in row:
                    call_market_data = row["call_options"].get("market_data", {})
                    ce_total_oi += int(call_market_data.get("oi", 0))

                # Check Put Option (PE)
                if stk in itm_pe_strikes and "put_options" in row:
                    put_market_data = row["put_options"].get("market_data", {})
                    pe_total_oi += int(put_market_data.get("oi", 0))

            difference = ce_total_oi - pe_total_oi

            return {
                "spot_price": spot_price,
                "atm_strike": atm_strike,
                "ce_total_oi": ce_total_oi,
                "pe_total_oi": pe_total_oi,
                "difference": difference,
                "failed": False
            }
        else:
            print(f"⚠️ Upstox Option Chain HTTP Status: {chain_res.status_code}")

    except Exception as e:
        print(f"❌ Upstox Data Fetch Error: {e}")

    return None


# ==================== REPORT GENERATOR ====================

def generate_dhan_report():
    tz_ist = pytz.timezone('Asia/Kolkata')
    today = datetime.datetime.now(tz_ist).strftime("%d-%b-%Y %I:%M %p")

    macro_sentiment, global_cues, fii_status = get_market_news_and_macro_sentiment()
    oi_data = get_upstox_option_chain()

    report = f"⚡ **UPSTOX LIVE MARKET ALERT (15 Min Update)** ⚡\n📅 `{today}`\n\n"

    # --- Section 1: Market Sentiment ---
    report += "📰 **1. MARKET SENTIMENT (News & Macro Data):**\n"
    report += f"• **Overall Bias:** {macro_sentiment}\n"
    report += f"• **FII/DII Trend:** `{fii_status}`\n"
    report += "\n" + "─" * 25 + "\n\n"

    # --- Section 2: Trade Signal ---
    report += "🎯 **2. TRADE SIGNAL (3 ITM Strikes OI Rule):**\n"

    if oi_data and not oi_data.get("failed", False):
        ce_oi = oi_data["ce_total_oi"]
        pe_oi = oi_data["pe_total_oi"]
        diff = oi_data["difference"]

        trade_signal = "🟡 **NO CLEAR SIGNAL (WAIT & WATCH)**"

        if pe_oi > 0 and ce_oi >= (pe_oi * 1.25):
            trade_signal = "🔴 **BUY PE (Call Writers Heavy by 25%+)**"
        elif ce_oi > 0 and pe_oi >= (ce_oi * 1.25):
            trade_signal = "🟢 **BUY CE (Put Writers Heavy by 25%+)**"

        ce_lakhs = format_lakhs(ce_oi).replace("+", "")
        pe_lakhs = format_lakhs(pe_oi).replace("+", "")
        diff_lakhs = format_lakhs(diff)

        report += f"• **Signal:** {trade_signal}\n"
        report += f"• **Nifty Spot:** `{oi_data['spot_price']:.1f}` (ATM: `{oi_data['atm_strike']}`)\n\n"

        report += "🔢 **3 ITM Strikes OI Breakup:**\n"
        report += f"• Total CE ITM OI: `{ce_lakhs}`\n"
        report += f"• Total PE ITM OI: `{pe_lakhs}`\n"
        report += f"• Difference (CE - PE): `{diff_lakhs}`\n\n"
    else:
        report += "⚠️ **DATA TEMPORARILY UNAVAILABLE**\n"
        report += "• *Upstox API Access Token configuration needed or market is closed.*\n\n"

    report += "💡 *Note: Automatic 15-minute interval live update.*"

    return report


if __name__ == "__main__":
    tz_ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(tz_ist)
    
    # Check: Monday to Friday ONLY
    if now.weekday() < 5:
        market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        if market_start <= now <= market_end:
            print(f"[{now.strftime('%I:%M %p IST')}] Market Open: Running Upstox Live Alert...")
            report = generate_dhan_report()
            send_telegram_message(report)
        else:
            print(f"[{now.strftime('%I:%M %p IST')}] Outside Market Hours. Alert Skipped.")
    else:
        print("Weekend - Market Closed. Alert Skipped.")
