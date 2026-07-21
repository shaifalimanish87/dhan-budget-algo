import os
import requests
import pandas as pd
import yfinance as yf
from ta.momentum import RSIIndicator
from dhanhq import dhanhq as DhanClient
from dhanhq.dhan_context import DhanContext
from dotenv import load_dotenv

load_dotenv()

# ==================== CONFIGURATION ====================
CLIENT_ID = os.getenv("DHAN_CLIENT_ID", "1112617852")
ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not ACCESS_TOKEN:
    raise ValueError("❌ ERROR: DHAN_ACCESS_TOKEN nahi mila! GitHub Secrets check karein.")

context = DhanContext(client_id=CLIENT_ID, access_token=ACCESS_TOKEN)
dhan = DhanClient(context)

MONITOR_INDICES = {
    "NIFTY": {
        "security_id": "13", 
        "yf_symbol": "^NSEI", 
        "lot_size": 65
    },
    "BANKNIFTY": {
        "security_id": "25", 
        "yf_symbol": "^NSEBANK", 
        "lot_size": 30
    }
}

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: 
        requests.post(url, json=payload)
    except Exception as e: 
        print(f"Telegram error: {e}")

def get_live_data_yfinance(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1d", interval="5m")
        if not df.empty:
            spot_price = float(df["Close"].iloc[-1])
            rsi_5m = float(RSIIndicator(close=df["Close"], window=min(14, len(df)-1)).rsi().iloc[-1])
            return spot_price, rsi_5m
    except Exception as e:
        print(f"yfinance error for {symbol}: {e}")
    return 0.0, 50.0

def fetch_option_chain_data(security_id):
    try:
        chain = dhan.get_option_chain(security_id=int(security_id), exchange_segment="NSE_FNO")
        if chain and chain.get('status') == 'success' and 'data' in chain:
            data = chain['data']
            df = pd.DataFrame(data if isinstance(data, list) else data.get('oc', []))
            
            if not df.empty and 'option_type' in df.columns and 'open_interest' in df.columns:
                total_call_oi = df[df['option_type'] == 'CE']['open_interest'].sum()
                total_put_oi = df[df['option_type'] == 'PE']['open_interest'].sum()
                pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 1.0
                return pcr, df
    except Exception as e: 
        print(f"Option Chain Error: {e}")
    return 1.0, None

def run_trading_engine():
    print("🚀 PRO-MODE: Auto-Trigger Scan Started...")
    now = pd.Timestamp.now(tz='Asia/Kolkata')
    
    # Live market hours check (9:15 AM to 3:30 PM IST)
    if now.weekday() >= 5 or now.hour < 9 or (now.hour == 9 and now.minute < 15) or (now.hour >= 15 and now.minute > 30):
        print("💤 Market is currently closed. Exiting safely.")
        return

    diagnostics = []

    for index_name, info in MONITOR_INDICES.items():
        sec_id = info["security_id"]
        yf_symbol = info["yf_symbol"]
        lot_size = info["lot_size"]

        # Realtime Spot & RSI
        current_spot, rsi_5m = get_live_data_yfinance(yf_symbol)
        
        # Realtime Option Chain & PCR
        pcr, chain_df = fetch_option_chain_data(sec_id)

        diagnostics.append(f"📊 *{index_name}*: Spot ₹{current_spot:.1f} | RSI 5m: {rsi_5m:.1f} | PCR: {pcr:.2f}")

        # EASY & SUPER RESPONSIVE SIGNAL LOGIC
        signal = None
        if rsi_5m >= 52 or pcr > 1.02:
            signal = "CE"
        elif rsi_5m <= 48 or pcr < 0.98:
            signal = "PE"

        if signal and chain_df is not None:
            price_col = 'last_traded_price' if 'last_traded_price' in chain_df.columns else ('last_price' if 'last_price' in chain_df.columns else None)
            
            if price_col:
                budget_contracts = chain_df[(chain_df['option_type'] == signal) & (chain_df[price_col] >= 1) & (chain_df[price_col] <= 350)]
                
                if not budget_contracts.empty:
                    best_contract = budget_contracts.sort_values(by=price_col, ascending=False).iloc[0]
                    live_premium = float(best_contract[price_col])
                    strike_price = best_contract.get('strike_price', 'ATM')
                    total_lot_cost = round(live_premium * lot_size, 2)
                    
                    target_premium = round(live_premium * 1.25, 2)
                    sl_premium = round(live_premium * 0.90, 2)

                    msg = (
                        f"🎯 *🔥 FAST TRADE SIGNAL: {index_name} 🔥*\n"
                        f"-------------------------------------\n"
                        f"📈 *Action:* BUY {strike_price} {signal}\n"
                        f"💵 *Premium:* ₹{live_premium} (Lot Cost: ₹{total_lot_cost})\n"
                        f"-------------------------------------\n"
                        f"🚀 *Target (25%):* ₹{target_premium}\n"
                        f"🛑 *StopLoss (10%):* ₹{sl_premium}\n"
                        f"-------------------------------------\n"
                        f"📍 *Spot:* ₹{current_spot:.1f} | *RSI 5m:* {rsi_5m:.1f} | *PCR:* {pcr:.2f}"
                    )
                    send_telegram_alert(msg)

    if diagnostics:
        send_telegram_alert("🔍 *LIVE SCAN REPORT*\n" + "\n".join(diagnostics))

    print("🔄 Execution successfully completed.")

if __name__ == "__main__":
    run_trading_engine()
