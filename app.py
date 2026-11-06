"""
GLOBAL INDICES DECIMAL ENGINE (ORIGINAL 30-NUMBER MODEL - ALL 4 INDICES)
- Strategy: 30-Number Continuous Span / Dual-Band (LTP ± 7 ∪ VWAP ± 7)
- Screen Lock: Exactly 15 minutes before official market close
- Hard-Lock: Locks permanently once lock time passes
"""

from datetime import datetime, time
import numpy as np
import pandas as pd
import pytz
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="Global Indices Decimal Engine",
    page_icon="🎯",
    layout="wide"
)

IST = pytz.timezone("Asia/Kolkata")

# STRICT 15-MINUTE PRE-CLOSE LOCK TIMINGS
INDEX_REGISTRY = {
    "Taiwan (TAIEX)": {
        "symbol": "^TWII",
        "close_h": 11, "close_m": 0,
        "lock_h": 10,  "lock_m": 45
    },
    "South Korea (KOSPI)": {
        "symbol": "^KS11",
        "close_h": 11, "close_m": 30,
        "lock_h": 11,  "lock_m": 15
    },
    "India (BSE Sensex)": {
        "symbol": "^BSESN",
        "close_h": 15, "close_m": 30,
        "lock_h": 15,  "lock_m": 15
    },
    "Germany (DAX)": {
        "symbol": "^GDAXI",
        "close_h": 22, "close_m": 0,
        "lock_h": 21,  "lock_m": 45
    }
}

def extract_decimal(price: float) -> int:
    try:
        if pd.isna(price) or price is None:
            return -1
        return int(f"{float(price):.2f}".split(".")[1])
    except Exception:
        return -1

def get_30_number_basket(ltp_dec: int, vwap_dec: int, target_size: int = 30) -> list:
    """Original dual-band logic (LTP ± 7 ∪ VWAP ± 7) expanded smoothly to 30 continuous numbers."""
    ltp_band = {(ltp_dec + k) % 100 for k in range(-7, 8)}
    vwap_band = {(vwap_dec + k) % 100 for k in range(-7, 8)}
    combined = ltp_band.union(vwap_band)
    
    # Bridge between LTP and VWAP if there is a gap to keep it continuous up to 30
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

def get_engine_data(symbol: str, lock_dt: datetime, is_locked: bool):
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
    ltp_dec = extract_decimal(ltp)
    snap_time = calc_df.index[-1].strftime("%I:%M %p IST")
    
    win = calc_df.tail(15)
    typ = (win["High"] + win["Low"] + win["Close"]) / 3.0
    vol = win["Volume"] if "Volume" in win.columns else pd.Series(0, index=win.index)
    vwap = float((typ * vol).sum() / vol.sum()) if vol.sum() > 0 else float(typ.mean())
    vwap_dec = extract_decimal(vwap)
    
    basket = get_30_number_basket(ltp_dec, vwap_dec, target_size=30)
    
    return {
        "ltp": ltp,
        "ltp_dec": ltp_dec,
        "vwap": vwap,
        "vwap_dec": vwap_dec,
        "basket": basket,
        "time": snap_time
    }

st.title("🎯 Global Indices Decimal Engine (Original 30-Number Model)")
st.caption("30-Number Span Across All 4 Indices | Strict 15-Minute Pre-Close Lock")

now_ist = datetime.now(IST)
cur_date = now_ist.date()

st.sidebar.markdown(f"**Current IST:** `{now_ist.strftime('%Y-%m-%d %I:%M:%S %p')}`")
if st.sidebar.button("🔄 Sync Feed"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("🔒 15m Pre-Close Hard-Lock Schedule")
for name, c in INDEX_REGISTRY.items():
    st.sidebar.write(f"• **{name.split()[0]}**: Locks at `{c['lock_h']:02d}:{c['lock_m']:02d}` (Close `{c['close_h']:02d}:{c['close_m']:02d}`)")

cols = st.columns(2)
for i, (name, cfg) in enumerate(INDEX_REGISTRY.items()):
    col = cols[i % 2]
    with col:
        st.subheader(f"📊 {name}")
        lock_dt = IST.localize(datetime.combine(cur_date, time(cfg["lock_h"], cfg["lock_m"])))
        is_locked = now_ist >= lock_dt
        
        with st.spinner(f"Computing {name}..."):
            data = get_engine_data(cfg["symbol"], lock_dt, is_locked)
            
        if not data:
            st.warning("Awaiting market ticks...")
            continue
            
        if is_locked:
            st.success(f"🔒 **HARD-LOCKED (15m Pre-Close)** [Tick: {data['time']}]")
        else:
            st.info(f"⏳ **RUNNING LIVE** (Locks at {cfg['lock_h']:02d}:{cfg['lock_m']:02d} IST)")
            
        m1, m2, m3 = st.columns(3)
        m1.metric("Snapshot LTP", f"{data['ltp']:,.2f}", f".{data['ltp_dec']:02d}")
        m2.metric("Snapshot VWAP", f"{data['vwap']:,.2f}", f".{data['vwap_dec']:02d}")
        m3.metric("Basket Count", f"{len(data['basket'])} Numbers")
        
        st.markdown("**🎯 Predicted 30-Number Basket:**")
        st.markdown(" ".join([f"`{n:02d}`" for n in data["basket"]]))
        st.markdown("---")
