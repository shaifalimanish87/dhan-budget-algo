import time
import requests
import pandas as pd
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
import yfinance as yf
import pytz
import warnings
from datetime import datetime

warnings.filterwarnings("ignore", category=FutureWarning)

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = "8987958487:AAHaPpZD2C4GRJ-Eu8JYPPLQxYVjSb8Aegk"
TELEGRAM_CHAT_ID = "1177543310"

# --- ALL MAJOR INDIAN INDICES + TOP STOCKS WATCHLIST ---
def get_watchlist():
    return {
        # 🔥 Corrected Yahoo Finance Symbols for Indian Indices
        "^NSEI": {"name": "NIFTY 50", "is_index": True, "index_type": "nifty"},
        "^NSEBANK": {"name": "BANK NIFTY", "is_index": True, "index_type": "banknifty"},
        "^BSESN": {"name": "SENSEX", "is_index": True, "index_type": "sensex"},
        "NIFTY_FIN_SERVICE.NS": {"name": "FIN NIFTY", "is_index": True, "index_type": "finnifty"},
        "NIFTY_MID_SELECT.NS": {"name": "MIDCAP NIFTY", "is_index": True, "index_type": "midcap"},
        
        # Top Stocks for F&O
        "RELIANCE.NS": {"name": "RELIANCE", "is_index": False, "index_type": None},
        "TCS.NS": {"name": "TCS", "is_index": False, "index_type": None},
        "HDFCBANK.NS": {"name": "HDFCBANK", "is_index": False, "index_type": None},
        "SBIN.NS": {"name": "SBIN", "is_index": False, "index_type": None},
        "ICICIBANK.NS": {"name": "ICICIBANK", "is_index": False, "index_type": None}
    }

# --- AUTOMATIC STRIKE PRICE CALCULATOR FOR ALL INDICES & STOCKS ---
def calculate_atm_strike(name, current_price, is_index, index_type):
    if is_index:
        if index_type == "nifty": base = 50
        elif index_type == "banknifty": base = 100
        elif index_type == "sensex": base = 100
        elif index_type == "finnifty": base = 50
        elif index_type == "midcap": base = 25
        else: base = 50
    else:
        if current_price > 5000: base = 100
        elif current_price > 2000: base = 50
        elif current_price > 1000: base = 20
        else: base = 10
        
    return int(base * round(current_price / base))

# --- QUANT ENGINE ---
def scan_accurate_market():
    watchlist = get_watchlist()
    print(f"🔄 Scanning All Indices & Stocks...")
    
    for symbol, info in watchlist.items():
        try:
            name = info["name"]
            is_index = info["is_index"]
            index_type = info["index_type"]
            
            df = yf.download(symbol, period="2d", interval="5m", progress=False)
            if df.empty or len(df) < 30:
                continue

            # Standard clean column structure
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0].lower() for col in df.columns]
            else:
                df.columns = [col.lower() for col in df.columns]

            # Using standard 'ta' library indicators
            rsi_series = RSIIndicator(close=df['close'], window=14).rsi()
            atr_series = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()

            current_price = round(float(df['close'].iloc[-2]), 2)
            rsi_value = float(rsi_series.iloc[-2]) if not pd.isna(rsi_series.iloc[-2]) else 50.0
            atr_value = float(atr_series.iloc[-2]) if not pd.isna(atr_series.iloc[-2]) else current_price * 0.002
            
            atm_strike = calculate_atm_strike(name, current_price, is_index, index_type)
            
            if is_index:
                target_mult = 2.0 if index_type in ["nifty", "finnifty", "midcap"] else 1.8
                sl_mult = 1.2
                est_premium = round(atr_value * 1.4, 2)
            else:
                target_mult = 2.5
                sl_mult = 1.5
                est_premium = round(atr_value * 1.2, 2)
                
            if est_premium < 2: est_premium = round(current_price * 0.01, 2)

            msg = None
            # 🟢 RSI > 52 = BULLISH (BUY CALL / CE)
            if rsi_value > 52:
                spot_target = round(current_price + (target_mult * atr_value), 2)
                spot_sl = round(current_price - (sl_mult * atr_value), 2)
                premium_target = round(est_premium + ((spot_target - current_price) * 0.50), 2)
                premium_sl = round(est_premium - ((current_price - spot_sl) * 0.50), 2)
                if premium_sl < 1: premium_sl = round(est_premium * 0.4, 2)
                
                msg = (f"⭐ *ACCURATE F&O SIGNAL* ⭐\n\n"
                       f"🟢 *ACTION: BUY CALL (CE)* 🚀\n"
                       f"👉 **{name} {atm_strike} CE**\n"
                       f"-------------------------\n"
                       f"💵 *Expected Premium Entry:* ₹{est_premium}\n"
                       f"🎯 *Premium Target:* ₹{premium_target}\n"
                       f"🛑 *Premium StopLoss:* ₹{premium_sl}\n"
                       f"-------------------------\n"
                       f"📈 _[Spot Chart Reference]_\n"
                       f"• Current Spot: ₹{current_price}\n"
                       f"• Spot Target: ₹{spot_target}\n"
                       f"• Spot StopLoss: ₹{spot_sl}\n\n"
                       f"💡 *How to Trade:* Apne broker app mein **{name} {atm_strike} CE** kholiye.")
            
            # 🔴 RSI < 48 = BEARISH (BUY PUT / PE)
            elif rsi_value < 48:
                spot_target = round(current_price - (target_mult * atr_value), 2)
                spot_sl = round(current_price + (sl_mult * atr_value), 2)
                premium_target = round(est_premium + ((current_price - spot_target) * 0.50), 2)
                premium_sl = round(est_premium - ((spot_sl - current_price) * 0.50), 2)
                if premium_sl < 1: premium_sl = round(est_premium * 0.4, 2)
                
                msg = (f"⭐ *ACCURATE F&O SIGNAL* ⭐\n\n"
                       f"🔴 *ACTION: BUY PUT (PE)* ⚠️\n"
                       f"👉 **{name} {atm_strike} PE**\n"
                       f"-------------------------\n"
                       f"💵 *Expected Premium Entry:* ₹{est_premium}\n"
                       f"🎯 *Premium Target:* ₹{premium_target}\n"
                       f"🛑 *Premium StopLoss:* ₹{premium_sl}\n"
                       f"-------------------------\n"
                       f"📈 _[Spot Chart Reference]_\n"
                       f"• Current Spot: ₹{current_price}\n"
                       f"• Spot Target: ₹{spot_target}\n"
                       f"• Spot StopLoss: ₹{spot_sl}\n\n"
                       f"💡 *How to Trade:* Apne broker app mein **{name} {atm_strike} PE** kholiye.")

            if msg:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
                time.sleep(1.5)
                
        except Exception as e:
            print(f"Error scanning {symbol}: {e}")

# --- MAIN RUNNER ---
if __name__ == "__main__":
    print("⚡ Ultra Hybrid Multi-Index F&O Engine Started...")
    IST = pytz.timezone('Asia/Kolkata')
    now = datetime.now(IST)

    if now.weekday() < 5 and (9, 15) <= (now.hour, now.minute) <= (15, 30):
        print(f"⏰ Market is Live. Running Full Scan: {now.strftime('%H:%M:%S')}")
        scan_accurate_market()
        print("Full multi-index scan completed successfully.")
    else:
        print(f"💤 Market Closed or Weekend. Current India Time: {now.strftime('%H:%M')}. Skipping scan.")
