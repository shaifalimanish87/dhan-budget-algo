import os
import time
import requests
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
from dhanhq import dhanhq as DhanClient
from dhanhq.dhan_context import DhanContext
import pytz
from datetime import datetime

# ==================== CONFIGURATION (GitHub Secrets) ====================
CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Dhan Context & Client Setup
context = DhanContext(client_id=CLIENT_ID, access_token=ACCESS_TOKEN)
dhan = DhanClient(context)

# Official Dhan Index Security IDs
MONITOR_INDICES = {
    "NIFTY 50": {"security_id": "13", "exchange_segment": "IDX_I", "lot_size": 75},
    "BANK NIFTY": {"security_id": "25", "exchange_segment": "IDX_I", "lot_size": 15},
    "FIN NIFTY": {"security_id": "27", "exchange_segment": "IDX_I", "lot_size": 40}
}

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: 
        requests.post(url, json=payload)
    except Exception as e: 
        print(f"Telegram error: {e}")

def get_live_ohlc(security_id, exchange_seg, interval):
    try:
        # Method 1: Official Dhan Intraday Daily Minute Charts API
        res = dhan.intraday_daily_minute_charts(
            security_id=str(security_id),
            exchange_segment=exchange_seg,
            instrument_type="INDEX"
        )
        
        # Fallback Method 2: If exchange_segment needs NSE_FNO
        if not res or res.get('status') != 'success' or 'data' not in res:
            res = dhan.intraday_daily_minute_charts(
                security_id=str(security_id),
                exchange_segment="NSE_FNO",
                instrument_type="INDEX"
            )

        df = pd.DataFrame()
        
        if isinstance(res, dict) and res.get('status') == 'success' and 'data' in res:
            data_content = res['data']
            # Dhan returns dict of arrays: {'open': [...], 'close': [...], 'start_time': [...]}
            if isinstance(data_content, dict):
                df = pd.DataFrame(data_content)
            elif isinstance(data_content, list):
                df = pd.DataFrame(data_content)
                
        if not df.empty:
            # Timestamp conversion
            if 'start_time' in df.columns:
                df['start_time'] = pd.to_datetime(df['start_time'], unit='s')
                df.set_index('start_time', inplace=True)
            elif 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
                df.set_index('timestamp', inplace=True)

            # Convert OHLC columns to float
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # Resample 1-min candles to target timeframe (5m / 15m)
            if str(interval) != '1':
                resampled_df = df.resample(f'{interval}min').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                }).dropna().reset_index()
                return resampled_df
            
            return df.reset_index()
            
    except Exception as e:
        print(f"OHLC Exception for {security_id}: {e}")
    return pd.DataFrame()

def run_trading_scan():
    IST = pytz.timezone('Asia/Kolkata')
    now = datetime.now(IST)
    
    scan_summary = []

    for index_name, info in MONITOR_INDICES.items():
        sec_id = info["security_id"]
        exch_seg = info["exchange_segment"]
        lot_size = info["lot_size"]

        df_5m = get_live_ohlc(sec_id, exch_seg, 5)
        df_15m = get_live_ohlc(sec_id, exch_seg, 15)

        if df_5m.empty or df_15m.empty:
            scan_summary.append(f"⚠️ *{index_name}*: Data Empty / API Issue")
            continue

        rsi_5m = RSIIndicator(close=df_5m['close'], window=14).rsi().iloc[-1]
        rsi_15m = RSIIndicator(close=df_15m['close'], window=14).rsi().iloc[-1]
        current_ema_50 = EMAIndicator(close=df_5m['close'], window=50).ema_indicator().iloc[-1]
        current_spot = df_5m['close'].iloc[-1]

        try:
            chain = dhan.get_option_chain(security_id=str(sec_id), exchange_segment="NSE_FNO")
            if not chain or chain.get('status') != 'success':
                scan_summary.append(f"⚠️ *{index_name}*: Option Chain Fetch Failed")
                continue
            chain_df = pd.DataFrame(chain['data'])
        except Exception as e:
            scan_summary.append(f"⚠️ *{index_name}*: Chain Exception")
            continue

        total_call_oi = chain_df[chain_df['option_type'] == 'CE']['open_interest'].sum()
        total_put_oi = chain_df[chain_df['option_type'] == 'PE']['open_interest'].sum()
        pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 1.0
        
        # Diagnostic Log
        scan_summary.append(
            f"📊 *{index_name}*: Spot ₹{current_spot:.1f} | RSI 5m: {rsi_5m:.1f} | PCR: {pcr:.2f}"
        )

        signal = None
        if rsi_5m > 50 and rsi_15m > 50 and current_spot > current_ema_50 and pcr > 1.0:
            signal = "CE"
        elif rsi_5m < 50 and rsi_15m < 50 and current_spot < current_ema_50 and pcr < 1.0:
            signal = "PE"

        if signal:
            # Budget Filter: ₹1 - ₹200 Bracket
            budget_contracts = chain_df[(chain_df['option_type'] == signal) & (chain_df['last_traded_price'] >= 1) & (chain_df['last_traded_price'] <= 200)]
            
            if not budget_contracts.empty:
                best_contract = budget_contracts.sort_values(by='last_traded_price', ascending=False).iloc[0]
                live_premium = best_contract['last_traded_price']
                strike_price = best_contract['strike_price']
                total_lot_cost = round(live_premium * lot_size, 2)
                
                target_premium = round(live_premium * 1.30, 2)
                sl_premium = round(live_premium * 0.85, 2)
                
                msg = (
                    f"🎯 *🔥 REAL-TIME DHAN SIGNAL 🔥*\n"
                    f"-------------------------------------\n"
                    f"📈 *Action:* BUY {index_name} {strike_price} {signal}\n"
                    f"💵 *Live Premium:* ₹{live_premium}\n"
                    f"📦 *Total Lot Cost:* ₹{total_lot_cost}\n"
                    f"-------------------------------------\n"
                    f"🎯 *Target (30%):* ₹{target_premium}\n"
                    f"🛑 *StopLoss (15%):* ₹{sl_premium}\n"
                    f"-------------------------------------\n"
                    f"⏱️ RSI 5m: {rsi_5m:.1f} | 15m: {rsi_15m:.1f} | Real PCR: {pcr:.2f}"
                )
                send_telegram_alert(msg)

    if scan_summary:
        report = "🔍 *DHAN LIVE SCAN REPORT*\n" + "\n".join(scan_summary)
        send_telegram_alert(report)

if __name__ == "__main__":
    send_telegram_alert("☀️ *DHAN LIVE SCANNING ENGINE ACTIVE*")
    run_trading_scan()
