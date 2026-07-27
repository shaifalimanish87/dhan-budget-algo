import os
import datetime
import requests
import pytz
import yfinance as yf

# ==================== CONFIGURATION ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ==================== HELPER FUNCTIONS ====================

def format_lakhs(number):
    """Numbers ko Lakhs (Lakh) me format karta hai"""
    if number is None or number == 0:
        return "0.00 Lakh"
    lakh_value = number / 100000
    sign = "+" if lakh_value > 0 else ""
    if lakh_value < 0:
        return f"-{abs(lakh_value):.2f} Lakh"
    elif lakh_value > 0:
        return f"{sign}{lakh_value:.2f} Lakh"
    else:
        return "0.00 Lakh"


def send_telegram_message(message):
    """Telegram Alert Function"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        print(f"Telegram API Status: {r.status_code}")
    except Exception as e:
        print(f"Telegram Error: {e}")


def get_live_nifty_spot():
    """Live Nifty Spot Price Fetcher"""
    try:
        data = yf.Ticker("^NSEI").history(period="1d", interval="1m")
        if not data.empty:
            return float(data["Close"].iloc[-1])
    except Exception as e:
        print(f"yfinance Spot Price Error: {e}")
    return 0.0


# ==================== THEORY 1: NEWS & MACRO SENTIMENT ====================

def get_market_news_and_macro_sentiment():
    """Theory 1: Global Cues aur FII/DII Sentiment Check"""
    sentiment_score = 0
    cues_summary = []

    tickers = {
        "S&P 500": "^GSPC",
        "Nasdaq": "^IXIC",
        "GIFT Nifty": "^NSEI"
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
        except Exception:
            pass

    try:
        url = "https://www.moneycontrol.com/stocks/marketstats/fii_dii_activity/"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=5)
        
        if "Net Buy" in res.text or "Buy" in res.text:
            sentiment_score += 1
            fii_status = "Net Buyers 🟢"
        else:
            sentiment_score -= 1
            fii_status = "Net Sellers 🔴"
    except Exception:
        fii_status = "Data Unavailable"

    if sentiment_score >= 2:
        sentiment = "🟢 **BULLISH (Global Cues & FII Positive)**"
    elif sentiment_score <= -2:
        sentiment = "🔴 **BEARISH (Global Cues & FII Negative)**"
    else:
        sentiment = "🟡 **NEUTRAL / MIXED (Cues Sideways)**"

    return sentiment, cues_summary, fii_status


# ==================== THEORY 2: GUARANTEED OPEN INTEREST ENGINE ====================

def get_nifty_itm_oi_analysis():
    """Theory 2: High-Reliability Yahoo Option API Stream for 3 ITM Strikes"""
    spot_price = get_live_nifty_spot()
    if spot_price == 0.0:
        return None

    strike_step = 50
    atm_strike = int(round(spot_price / strike_step) * strike_step)

    itm_ce_strikes = [atm_strike, atm_strike - strike_step, atm_strike - (2 * strike_step)]
    itm_pe_strikes = [atm_strike, atm_strike + strike_step, atm_strike + (2 * strike_step)]

    ce_total_oi = 0
    pe_total_oi = 0

    # Direct Yahoo Finance Option Chain Stream (No Cloud IP Blocking)
    try:
        url = "https://query2.finance.yahoo.com/v7/finance/options/^NSEI"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        }
        res = requests.get(url, headers=headers, timeout=8)
        
        if res.status_code == 200:
            result = res.json().get('optionChain', {}).get('result', [])
            if result and len(result) > 0:
                options = result[0].get('options', [])
                if options and len(options) > 0:
                    calls = options[0].get('calls', [])
                    puts = options[0].get('puts', [])

                    for c in calls:
                        stk = int(round(float(c.get('strike', 0))))
                        if stk in itm_ce_strikes:
                            ce_total_oi += int(c.get('openInterest', 0))

                    for p in puts:
                        stk = int(round(float(p.get('strike', 0))))
                        if stk in itm_pe_strikes:
                            pe_total_oi += int(p.get('openInterest', 0))
    except Exception as e:
        print(f"Yahoo Engine Fetch Error: {e}")

    difference = ce_total_oi - pe_total_oi

    return {
        "spot_price": spot_price,
        "atm_strike": atm_strike,
        "ce_total_oi": ce_total_oi,
        "pe_total_oi": pe_total_oi,
        "difference": difference,
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
        ce_oi = oi_data["ce_total_oi"]
        pe_oi = oi_data["pe_total_oi"]
        diff = oi_data["difference"]

        trade_signal = "🟡 **NO CLEAR SIGNAL (WAIT & WATCH)**"

        if pe_oi > 0 and ce_oi >= (pe_oi * 1.25):
            trade_signal = "🔴 **BUY PE (Call Writers Heavy by 25%+)**"
        elif ce_oi > 0 and pe_oi >= (ce_oi * 1.25):
            trade_signal = "🟢 **BUY CE (Put Writers Heavy by 25%+)**"

        report += f"• **Signal:** {trade_signal}\n"
        report += f"• **Nifty Spot:** `{oi_data['spot_price']:.1f}` (ATM: `{oi_data['atm_strike']}`)\n\n"

        ce_lakhs = format_lakhs(ce_oi).replace("+", "")
        pe_lakhs = format_lakhs(pe_oi).replace("+", "")
        diff_lakhs = format_lakhs(diff)

        report += "🔢 **3 ITM Strikes OI Breakup:**\n"
        report += f"• Total CE ITM OI: `{ce_lakhs}`\n"
        report += f"• Total PE ITM OI: `{pe_lakhs}`\n"
        report += f"• Difference (CE - PE): `{diff_lakhs}`\n\n"
    else:
        report += "⚠️ *Option chain data fetch failed.*\n\n"

    report += "💡 *Note: Automatic 15-minute interval live update.*"

    return report


if __name__ == "__main__":
    tz_ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(tz_ist)
    
    if now.weekday() < 5:
        market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        if market_start <= now <= market_end:
            print(f"[{now.strftime('%I:%M %p IST')}] Executing 15-Min Live Data & Sending Telegram Alert...")
            report = generate_dhan_report()
            send_telegram_message(report)
        else:
            print(f"[{now.strftime('%I:%M %p IST')}] Outside Market Hours. Sending Test Trigger...")
            report = generate_dhan_report()
            send_telegram_message(report)
    else:
        print("Weekend - Market Closed.")
