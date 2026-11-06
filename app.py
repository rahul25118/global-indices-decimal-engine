"""
ROBUST ZERO-LAG GLOBAL DECIMAL ENGINE (WITH FAILSAFE ARCHITECTURE)
Features:
- Primary: Direct 0-Lag Endpoints (BSE, TWSE, Naver/KRX, Boerse Frankfurt)
- Secondary: Automatic failover to Yahoo EOD/Intraday when exchange blocks server IP
- Permanent 15m Pre-Close Hard-Lock
"""

import json
import time
from datetime import datetime, time as dtime
import numpy as np
import pandas as pd
import pytz
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="Global Indices Decimal Engine",
    page_icon="⚡",
    layout="wide"
)

IST = pytz.timezone("Asia/Kolkata")

INDEX_REGISTRY = {
    "Taiwan (TAIEX)": {
        "id": "TAIEX",
        "yf_symbol": "^TWII",
        "close_h": 11, "close_m": 0,
        "lock_h": 10,  "lock_m": 45
    },
    "South Korea (KOSPI)": {
        "id": "KOSPI",
        "yf_symbol": "^KS11",
        "close_h": 11, "close_m": 30,
        "lock_h": 11,  "lock_m": 15
    },
    "India (BSE Sensex)": {
        "id": "SENSEX",
        "yf_symbol": "^BSESN",
        "close_h": 15, "close_m": 30,
        "lock_h": 15,  "lock_m": 15
    },
    "Germany (DAX)": {
        "id": "DAX",
        "yf_symbol": "^GDAXI",
        "close_h": 22, "close_m": 0,
        "lock_h": 21,  "lock_m": 45
    }
}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9"
}

def extract_decimal(price: float) -> int:
    try:
        if pd.isna(price) or price is None:
            return -1
        return int(f"{float(price):.2f}".split(".")[1])
    except Exception:
        return -1

def get_30_number_basket(ltp_dec: int, vwap_dec: int, target_size: int = 30) -> list:
    ltp_band = {(ltp_dec + k) % 100 for k in range(-7, 8)}
    vwap_band = {(vwap_dec + k) % 100 for k in range(-7, 8)}
    combined = ltp_band.union(vwap_band)
    
    dist_cw = (vwap_dec - ltp_dec) % 100
    dist_ccw = (ltp_dec - vwap_dec) % 100
    bridge = set(combined)
    
    if dist_cw <= dist_ccw:
        for i in range(dist_cw + 1):
            bridge.add((ltp_dec + i) % 100)
    else:
        for i in range(dist_ccw + 1):
            bridge.add((vwap_dec + i) % 100)
            
    curr_basket = sorted(list(bridge))
    pad = target_size - len(curr_basket)
    if pad > 0:
        left_pad = pad // 2
        right_pad = pad - left_pad
        left_min = curr_basket[0]
        right_max = curr_basket[-1]
        for k in range(1, left_pad + 1):
            bridge.add((left_min - k) % 100)
        for k in range(1, right_pad + 1):
            bridge.add((right_max + k) % 100)
            
    return sorted(list(bridge))[:target_size]

# ==============================================================================
# DATA FETCHER WITH AUTOMATIC FALLBACK
# ==============================================================================

def fetch_bse_sensex():
    try:
        url = "https://api.bseindia.com/BseIndiaAPI/api/GetSensexData/w"
        headers = dict(BROWSER_HEADERS)
        headers["Referer"] = "https://www.bseindia.com/"
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 200 and r.text.strip().startswith("{"):
            data = r.json()
            ltp = float(str(data.get("curval", "0")).replace(",", ""))
            high = float(str(data.get("high", ltp)).replace(",", ""))
            low = float(str(data.get("low", ltp)).replace(",", ""))
            if ltp > 0:
                return {"ltp": ltp, "vwap": (high + low + ltp) / 3.0, "time": f"{data.get('curtime', 'Live')} (BSE Direct)"}
    except Exception:
        pass
    return None

def fetch_taiwan():
    try:
        ts = int(time.time() * 1000)
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0&_={ts}"
        headers = dict(BROWSER_HEADERS)
        headers["Referer"] = "https://mis.twse.com.tw/"
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 200 and r.text.strip().startswith("{"):
            data = r.json()
            info = data["msgArray"][0]
            ltp = float(info.get("z", info.get("y", "0")))
            high = float(info.get("h", ltp))
            low = float(info.get("l", ltp))
            if ltp > 0:
                return {"ltp": ltp, "vwap": (high + low + ltp) / 3.0, "time": f"{info.get('t', 'Live')} (TWSE Direct)"}
    except Exception:
        pass
    return None

def fetch_kospi_direct():
    try:
        url = "https://m.stock.naver.com/api/index/KOSPI/basic"
        headers = dict(BROWSER_HEADERS)
        headers["Referer"] = "https://m.stock.naver.com/"
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 200 and r.text.strip().startswith("{"):
            data = r.json()
            ltp = float(str(data.get("nowValue", "0")).replace(",", ""))
            high = float(str(data.get("highValue", ltp)).replace(",", ""))
            low = float(str(data.get("lowValue", ltp)).replace(",", ""))
            if ltp > 0:
                return {"ltp": ltp, "vwap": (high + low + ltp) / 3.0, "time": "KRX Direct"}
    except Exception:
        pass
    return None

def fetch_dax_direct():
    try:
        url = "https://api.boerse-frankfurt.de/v1/data/quote_box/single?isin=DE0008469008"
        headers = dict(BROWSER_HEADERS)
        headers["client-date"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 200 and r.text.strip().startswith("{"):
            data = r.json()
            ltp = float(data.get("lastPrice", 0.0))
            high = float(data.get("highPrice", ltp))
            low = float(data.get("lowPrice", ltp))
            if ltp > 0:
                return {"ltp": ltp, "vwap": (high + low + ltp) / 3.0, "time": "Boerse Frankfurt Direct"}
    except Exception:
        pass
    return None

def fetch_failsafe(symbol: str, lock_dt: datetime, is_locked: bool):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="5d", interval="5m")
        if df.empty or "Close" not in df.columns:
            return None
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)
        df["Date"] = df.index.date
        today = lock_dt.date()
        day_df = df[df["Date"] == today].copy()
        if day_df.empty:
            latest_date = df["Date"].max()
            day_df = df[df["Date"] == latest_date].copy()
            is_locked = True
        calc_df = day_df[day_df.index <= lock_dt] if is_locked else day_df
        if calc_df.empty:
            calc_df = day_df.copy()
        last_row = calc_df.iloc[-1]
        ltp = float(last_row["Close"])
        win = calc_df.tail(15)
        typ = (win["High"] + win["Low"] + win["Close"]) / 3.0
        vol = win["Volume"] if "Volume" in win.columns else pd.Series(0, index=win.index)
        vwap = float((typ * vol).sum() / vol.sum()) if vol.sum() > 0 else float(typ.mean())
        return {
            "ltp": ltp,
            "vwap": vwap,
            "time": f"{calc_df.index[-1].strftime('%I:%M %p IST')} (Feed)"
        }
    except Exception:
        return None

# ==============================================================================
# UI RENDER
# ==============================================================================

st.title("⚡ Zero-Lag Global Decimal Engine")
st.caption("Direct Exchange Endpoints with Auto-Failsafe | 30-Number Solid Span")

now_ist = datetime.now(IST)
cur_date = now_ist.date()

st.sidebar.markdown(f"**Current IST:** `{now_ist.strftime('%Y-%m-%d %I:%M:%S %p')}`")
if st.sidebar.button("🔄 Sync Feed"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("🔒 Strict Lock Schedule")
for name, c in INDEX_REGISTRY.items():
    st.sidebar.write(f"• **{name.split()[0]}**: Locks `{c['lock_h']:02d}:{c['lock_m']:02d}`")

cols = st.columns(2)

for i, (name, cfg) in enumerate(INDEX_REGISTRY.items()):
    col = cols[i % 2]
    with col:
        st.subheader(f"📊 {name}")
        lock_dt = IST.localize(datetime.combine(cur_date, dtime(cfg["lock_h"], cfg["lock_m"])))
        is_locked = now_ist >= lock_dt
        
        data = None
        # Try direct 0-lag endpoint during live market
        if not is_locked:
            if cfg["id"] == "SENSEX":
                data = fetch_bse_sensex()
            elif cfg["id"] == "TAIEX":
                data = fetch_taiwan()
            elif cfg["id"] == "KOSPI":
                data = fetch_kospi_direct()
            elif cfg["id"] == "DAX":
                data = fetch_dax_direct()
                
        # If direct feed failed, server is blocked, or market is locked, use failsafe
        if not data:
            data = fetch_failsafe(cfg["yf_symbol"], lock_dt, is_locked)
            
        if not data:
            st.error("Market session data loading...")
            st.markdown("---")
            continue
            
        ltp_dec = extract_decimal(data["ltp"])
        vwap_dec = extract_decimal(data["vwap"])
        basket = get_30_number_basket(ltp_dec, vwap_dec, target_size=30)
        
        if is_locked:
            st.success(f"🔒 **HARD-LOCKED (15m Pre-Close)** [Tick: {data['time']}]")
        else:
            st.info(f"⏳ **0-LAG LIVE FEED** (Locks at {cfg['lock_h']:02d}:{cfg['lock_m']:02d} IST)")
            
        m1, m2, m3 = st.columns(3)
        m1.metric("Exchange LTP", f"{data['ltp']:,.2f}", f".{ltp_dec:02d}")
        m2.metric("Exchange VWAP", f"{data['vwap']:,.2f}", f".{vwap_dec:02d}")
        m3.metric("Basket Count", f"{len(basket)} Numbers")
        
        st.markdown("**🎯 Predicted 30-Number Basket:**")
        st.markdown(" ".join([f"`{n:02d}`" for n in basket]))
        st.markdown("---")
