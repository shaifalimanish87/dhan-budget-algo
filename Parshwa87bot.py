import datetime
import requests
import yfinance as yf
from dhanhq import dhanhq
import os

# ==================== CONFIGURATION ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DHAN_CLIENT_ID = os.getenv("DHAN_CLIENT_ID", "1112617852")
DHAN_ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN")

# Dhan Client Initialize
dhan = dhanhq(DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN)


# ==================== HELPER FUNCTIONS ====================

def format_lakhs(number):
    """Numbers ko Lakhs (Lakh) me format karta hai"""
    if number is None:
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
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")


def get_current_expiry_date():
    """Dhan API se live expiry list me se sabse paas wali expiry auto-fetch karta hai"""
    try:
        exp_data = dhan.get_expiry_list(under_security_id=13, under_exchange_segment="NSE_INDEX")
        if exp_data.get("status") == "success" and exp_data.get("data"):
            expiry_dates = sorted(exp_data["data"])
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            valid_expiries = [exp for exp in expiry_dates if exp >= today_str]
            if valid_expiries:
                return valid_expiries[0]
    except Exception as e:
        print(f"Expiry Fetch Error: {e}")
    return datetime.datetime.now().strftime("%Y-%m-%d")


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


# ==================== THEORY 2: 3 ITM STRIKES OI LOGIC ====================

def get_nifty_itm_oi_analysis():
    """Theory 2: Live 3 ITM CE vs PE OI Analysis"""
    try:
        quote_data = dhan.get_market_quote(
            exchange_segment=dhan.NSE_FNO, security_id="13"
        )

        if quote_data.get("status") != "success":
            return None

        spot_price = quote_data["data"]["last_price"]
        strike_step = 50
        atm_strike = round(spot_price / strike_step) * strike_step

        current_expiry = get_current_expiry_date()

        oc_response = dhan.option_chain(
            under_security_id=13,
            under_exchange_segment="NSE_INDEX",
            expiry=current_expiry,
        )

        if oc_response.get("status") != "success":
            return {
                "spot_price": spot_price,
                "atm_strike": atm_strike,
                "ce_total_oi": 0,
                "pe_total_oi": 0,
                "difference": 0,
                "error": "Option chain fetch failed",
            }

        oc_data = oc_response.get("data", {})

        itm_ce_strikes = [atm_strike, atm_strike - strike_step, atm_strike - (2 * strike_step)]
        itm_pe_strikes = [atm_strike, atm_strike + strike_step, atm_strike + (2 * strike_step)]

        ce_total_oi = 0
        pe_total_oi = 0

        for item in oc_data:
            strike = item.get("strike_price")

            if strike in itm_ce_strikes and "ce" in item:
                ce_total_oi += item["ce"].get("oi", 0)

            if strike in itm_pe_strikes and "pe" in item:
                pe_total_oi += item["pe"].get("oi", 0)

        difference = ce_total_oi - pe_total_oi

        return {
            "spot_price": spot_price,
            "atm_strike": atm_strike,
            "ce_total_oi": ce_total_oi,
            "pe_total_oi": pe_total_oi,
            "difference": difference,
        }

    except Exception as e:
        print(f"Error calculating ITM OI: {e}")
        return None


# ==================== REPORT GENERATOR ====================

def generate_dhan_report():
    today = datetime.datetime.now().strftime("%d-%b-%Y %I:%M %p")

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

    if oi_data and "error" not in oi_data:
        ce_oi = oi_data["ce_total_oi"]
        pe_oi = oi_data["pe_total_oi"]
        diff = oi_data["difference"]

        trade_signal = "🟡 **NO CLEAR SIGNAL (WAIT & WATCH)**"

        if pe_oi > 0 and ce_oi >= (pe_oi * 1.25):
            trade_signal = "🔴 **BUY PE (Call Writers Heavy by 25%+)**"
        elif ce_oi > 0 and pe_oi >= (ce_oi * 1.25):
            trade_signal = "🟢 **BUY CE (Put Writers Heavy by 25%+)**"

        report += f"• **Signal:** {trade_signal}\n"
        report += f"• **Nifty Spot:** `{oi_data['spot_price']}` (ATM: `{oi_data['atm_strike']}`)\n\n"

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
    now = datetime.datetime.now()
    if now.weekday() < 5:
        market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        if market_start <= now <= market_end:
            print(f"[{now.strftime('%I:%M %p')}] Executing 15-Min Live Data & Sending Telegram Alert...")
            report = generate_dhan_report()
            send_telegram_message(report)
        else:
            print(f"[{now.strftime('%I:%M %p')}] Outside Market Hours (09:15 AM - 03:30 PM).")
    else:
        print("Weekend - Market Closed.")
