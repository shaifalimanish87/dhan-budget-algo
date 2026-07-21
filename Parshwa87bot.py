import os
import requests
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
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
    "NIFTY": {"security_id": "13", "exchange_segment": "IDX_I", "lot_size": 65},
    "BANKNIFTY": {"security_id": "25", "exchange_segment": "IDX_I", "lot_size": 30}
}

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: 
        r = requests.post(url, json=payload)
        print(f"Telegram API Status: {r.status_code}")
    except Exception as e: 
        print(f"Telegram error: {e}")

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
                
                # Fetch spot price from option chain object
                spot_price = 0.0
                if 'underlying_value' in df.columns and not df['underlying_value'].dropna().empty:
                    spot_price = float(df['underlying_value'].iloc[0])
                elif 'last_traded_price' in df.columns:
                    spot_price = float(df['last_traded_price'].mean())
                    
                return pcr, df, spot_price
    except Exception as e: 
        print(f"Option Chain Error: {e}")
    return 1.0, None, 0.0

def get_live_ohlc(security_id, exchange_seg, interval):
    try:
        tz_now = pd.Timestamp.now(tz='Asia/Kolkata')
        today_str = tz_now.strftime('%Y-%m-%d')
        
        data = dhan.historical_minute_charts(
            security_id=str(security_id),
            exchange_segment=exchange_seg, 
            instrument_type="INDEX",
            from_date=today_str,
            to_date=today_str
        )
        
        if data and data.get('status') == 'success' and 'data' in data:
            df = pd.DataFrame(data['data'])
            if 'start_time' in df.columns:
                df['start_time'] = pd.to_datetime(df['start_time'], unit='s')
                df.set_index('start_time', inplace=True)
            
            if str(interval) != '1':
                resampled_df = df.resample(f'{interval}min').agg({
                    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                }).dropna().reset_index()
                return resampled_df
            return df.reset_index()
    except Exception as e: 
        print(f"OHLC Error for {security_id}: {e}")
    return pd.DataFrame()

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
        exch_seg = info["exchange_segment"]
        lot_size = info["lot_size"]

        pcr, chain_df, chain_spot = fetch_option_chain_data(sec_id)
        df_5m = get_live_ohlc(sec_id, exch_seg, 5)

        # Smart Spot Price & RSI Selection
        if not df_5m.empty and len(df_5m) >= 2 and 'close' in df_5m.columns:
            rsi_5m = RSIIndicator(close=df_5m['close'], window=min(14, len(df_5m)-1)).rsi().iloc[-1]
            current_spot = df_5m['close'].iloc[-1]
        else:
            rsi_5m = 50.0  # Default RSI fallback
            current_spot = chain_spot

        # Diagnostic report line
        diagnostics.append(f"📊 *{index_name}*: Spot ₹{current_spot:.1f} | RSI 5m: {rsi_5m:.1f} | PCR: {pcr:.2f}")

        # Signal Logic
        signal = None
        if rsi_5m > 48 or pcr >= 1.05:
            signal = "CE"
        elif rsi_5m < 52 or pcr <= 0.95:
            signal = "PE"

        if signal and chain_df is not None:
            price_col = 'last_traded_price' if 'last_traded_price' in chain_df.columns else ('last_price' if 'last_price' in chain_df.columns else None)
            
            if price_col:
                budget_contracts = chain_df[(chain_df['option_type'] == signal) & (chain_df[price_col] >= 1) & (chain_df[price_col] <= 300)]
                
                if not budget_contracts.empty:
                    best_contract = budget_contracts.sort_values(by=price_col, ascending=False).iloc[0]
                    live_premium = best_contract[price_col]
                    strike_price = best_contract.get('strike_price', 'ATM')
                    total_lot_cost = round(live_premium * lot_size, 2)
                    
                    target_premium = round(live_premium * 1.25, 2)
                    sl_premium = round(live_premium * 0.90, 2)

                    msg = (
                        f"🎯 *🔥 ALGO ALERT: {index_name} MOMENTUM 🔥*\n"
                        f"-------------------------------------\n"
                        f"📈 *Action:* BUY {strike_price} {signal}\n"
                        f"💵 *Premium:* ₹{live_premium} (Lot Cost: ₹{total_lot_cost})\n"
                        f"📊 *PCR:* {pcr:.2f} | *RSI 5m:* {rsi_5m:.1f}\n"
                        f"-------------------------------------\n"
                        f"🚀 *Target (25%):* ₹{target_premium}\n"
                        f"🛑 *StopLoss (10%):* ₹{sl_premium}\n"
                        f"-------------------------------------\n"
                        f"📍 *Spot Price:* ₹{current_spot:.1f}"
                    )
                    send_telegram_alert(msg)

    if diagnostics:
        send_telegram_alert("🔍 *LIVE SCAN REPORT*\n" + "\n".join(diagnostics))

    print("🔄 Execution successfully completed.")

if __name__ == "__main__":
    run_trading_engine()
