import os
import datetime
import requests
import pytz
import time
import yfinance as yf

# ==================== CONFIGURATION ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


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
        print(f"Telegram API Response Status: {r.status_code}")
    except Exception as e:
        print(f"Telegram Post Error: {e}")


def get_live_nifty_spot():
    """Live Nifty Spot Price Fetcher with Logging"""
    try:
        data = yf.Ticker("^NSEI").history(period="1d", interval="1m")
        if not data.empty:
            spot = float(data["Close"].iloc[-1])
            print(f"✅ Nifty Spot Price Fetched: {spot}")
            return spot
    except Exception as e:
        print(f"❌ yfinance Spot Price Fetch Error: {e}")
    return 0.0


# ==================== THEORY 1: NEWS & MACRO SENTIMENT ====================

def get_market_news_and_macro_sentiment():
    """Theory 1: Global Cues aur FII/DII Sentiment Check"""
    sentiment_score = 0
    cues_summary = []

    # GIFT Nifty Proxy & Major US Indices
    tickers = {
        "S&P 500": "^GSPC",
        "Nasdaq": "^IXIC",
        "GIFT Nifty Proxy": "^NSEI"  # Fallback Index Tracking
    }

    for name, ticker in tickers.items():
        try:
            data = yf.Ticker(ticker).history(period="2d")
            if len(data) >= 2:
                prev_close = data["Close"].iloc[-2]
                curr_close = data["Close"].iloc[-1]
                p_change = ((curr_close - prev_close) / prev_close) * 100

                if p_change > 0.3:
                    sentiment_score += 1
                elif p_change < -0.3:
                    sentiment_score -= 1
                
                sign = "+" if p_change > 0 else ""
                cues_summary.append(f"{name}: `{sign}{p_change:.2f}%`")
        except Exception as e:
            print(f"⚠️ Error fetching {name}: {e}")

    # Robust FII/DII Parsing
    fii_status = "Data Unavailable ⚠️"
    try:
        url = "https://www.moneycontrol.com/stocks/marketstats/fii_dii_activity/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            content = res.text.lower()
            if "net buy" in content or "net buyer" in content:
                sentiment_score += 1
                fii_status = "Net Buyers 🟢"
            elif "net sell" in content or "net seller" in content:
                sentiment_score -= 1
                fii_status = "Net Sellers 🔴"
            else:
                fii_status = "Neutral / Balanced 🟡"
    except Exception as e:
        print(f"⚠️ FII/DII Scraping Error: {e}")

    if sentiment_score >= 2:
        sentiment = "🟢 **BULLISH (Global Cues & FII Positive)**"
    elif sentiment_score <= -2:
        sentiment = "🔴 **BEARISH (Global Cues & FII Negative)**"
    else:
        sentiment = "🟡 **NEUTRAL / MIXED (Cues Sideways)**"

    return sentiment, cues_summary, fii_status


# ==================== THEORY 2: ROBUST NSE DIRECT SESSION ENGINE ====================

def fetch_nse_option_chain_with_retry():
    """NSE Live Option Chain with Retries, Header Spoofing & Session Warmup"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.nseindia.com/option-chain',
    }

    session = requests.Session()
    session.headers.update(headers)

    # Retry loop (Max 3 attempts with delay)
    for attempt in range(1, 4):
        try:
            print(f"🔄 Attempt {attempt}: Warming up NSE Session Cookies...")
            # Step 1: Visit main site to capture valid cookies
            home_resp = session.get("https://www.nseindia.com", timeout=6)
            if home_resp.status_code != 200:
                print(f"⚠️ NSE Home returned Status: {home_resp.status_code}")
            
            time.sleep(1)  # Small delay to mimic human behavior

            # Step 2: Fetch actual Option Chain JSON API
            api_url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
            api_resp = session.get(api_url, timeout=8)
            
            print(f"📊 NSE API Status Code: {api_resp.status_code}")

            if api_resp.status_code == 200:
                json_data = api_resp.json()
                if "records" in json_data and "data" in json_data["records"]:
                    print("✅ Successfully Received NSE Live Option Chain JSON Data!")
                    return json_data["records"]["data"]
            elif api_resp.status_code == 403:
                print("🚫 NSE 403 Forbidden: GitHub US IP Blocked by NSE Cloud Shield.")
            
        except Exception as e:
            print(f"❌ Attempt {attempt} Failed: {e}")
        
        time.sleep(2)  # Wait before retrying

    return None


def get_nifty_itm_oi_analysis():
    """Calculates 3 ITM Strikes OI using robust session handling"""
    spot_price = get_live_nifty_spot()
    if spot_price == 0.0:
        return None

    strike_step = 50
    atm_strike = int(round(spot_price / strike_step) * strike_step)

    itm_ce_strikes = [atm_strike, atm_strike - strike_step, atm_strike - (2 * strike_step)]
    itm_pe_strikes = [atm_strike, atm_strike + strike_step, atm_strike + (2 * strike_step)]

    records = fetch_nse_option_chain_with_retry()

    if not records:
        print("⚠️ Failed to retrieve NSE option chain data after retries.")
        return {
            "spot_price": spot_price,
            "atm_strike": atm_strike,
            "ce_total_oi": None,
            "pe_total_oi": None,
            "difference": None,
            "failed": True
        }

    ce_total_oi = 0
    pe_total_oi = 0

    for r in records:
        stk = int(round(float(r.get('strikePrice', 0))))
        if stk in itm_ce_strikes and 'CE' in r:
            ce_total_oi += int(r['CE'].get('openInterest', 0))
        if stk in itm_pe_strikes and 'PE' in r:
            pe_total_oi += int(r['PE'].get('openInterest', 0))

    difference = ce_total_oi - pe_total_oi

    return {
        "spot_price": spot_price,
        "atm_strike": atm_strike,
        "ce_total_oi": ce_total_oi,
        "pe_total_oi": pe_total_oi,
        "difference": difference,
        "failed": False
    }


# ==================== REPORT GENERATOR ====================

def generate_dhan_report():
    tz_ist = pytz.timezone('Asia/Kolkata')
    today = datetime.datetime.now(tz_ist).strftime("%d-%b-%Y %I:%M %p")

    macro_sentiment, global_cues, fii_status = get_market_news_and_macro_sentiment()
    oi_data = get_nifty_itm_oi_analysis()

    report = f"⚡ **DHAN LIVE MARKET ALERT (15 Min Update)** ⚡\n📅 `{today}`\n\n"

    # --- Theory 1 Section ---
    report += "📰 **1. MARKET SENTIMENT (News & Macro Data):**\n"
    report += f"• **Overall Bias:** {macro_sentiment}\n"
    report += f"• **FII/DII Trend:** `{fii_status}`\n"
    if global_cues:
        report += f"• **Global Cues:** " + ", ".join(global_cues) + "\n"
    report += "\n" + "─" * 25 + "\n\n"

    # --- Theory 2 Section ---
    report += "🎯 **2. TRADE SIGNAL (3 ITM Strikes OI Rule):**\n"

    if oi_data:
        if oi_data.get("failed", False) or oi_data["ce_total_oi"] is None:
            trade_signal = "⚠️ **DATA BLOCKED / UNAVAILABLE (NSE Cloud IP Protection)**"
            ce_lakhs = "Data Unavailable ⚠️"
            pe_lakhs = "Data Unavailable ⚠️"
            diff_lakhs = "Data Unavailable ⚠️"
        else:
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
        report += "⚠️ *Market Data Fetch Error.*\n\n"

    report += "💡 *Note: Automatic 15-minute interval live update.*"

    return report


if __name__ == "__main__":
    tz_ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(tz_ist)
    
    # Check: Monday to Friday ONLY
    if now.weekday() < 5:
        market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        # Sirf live market hours ke dauran hi alert jayega
        if market_start <= now <= market_end:
            print(f"[{now.strftime('%I:%M %p IST')}] Market Open: Executing 15-Min Live Data Alert...")
            report = generate_dhan_report()
            send_telegram_message(report)
        else:
            print(f"[{now.strftime('%I:%M %p IST')}] Outside Market Hours (9:15 AM - 3:30 PM). Alert Skipped.")
    else:
        print("Weekend - Market Closed. Alert Skipped.")
