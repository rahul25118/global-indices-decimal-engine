"""
HYBRID GLOBAL INDICES DECIMAL ENGINE
- Taiwan, KOSPI, Sensex: 15-Number Sniper Cluster (5 Anchors with ±1 cushion)
- Germany (DAX): 30-Number Continuous Bridge Model
- Strict Hard-Lock: Locks exactly 15 minutes before close and never drifts
"""

from datetime import date, datetime, time
import numpy as np
import pandas as pd
import pytz
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="Decimal Engine Hybrid",
    page_icon="🎯",
    layout="wide"
)

IST = pytz.timezone("Asia/Kolkata")

# OFFICIAL SCHEDULES & 15-MIN PRE-CLOSE HARD-LOCK
INDEX_REGISTRY = {
    "Taiwan (TAIEX)": {
        "symbol": "^TWII",
        "close_h": 11, "close_m": 0,
        "lock_h": 10,  "lock_m": 45,
        "model": "cluster_15"
    },
    "South Korea (KOSPI)": {
        "symbol": "^KS11",
        "close_h": 11, "close_m": 30,
        "lock_h": 11,  "lock_m": 15,
        "model": "cluster_15"
    },
    "India (BSE Sensex)": {
        "symbol": "^BSESN",
        "close_h": 15, "close_m": 30,
        "lock_h": 15,  "lock_m": 15,
        "model": "cluster_15"
    },
    "Germany (DAX)": {
        "symbol": "^GDAXI",
        "close_h": 22, "close_m": 0,
        "lock_h": 21,  "lock_m": 45,
        "model": "bridge_30"
    }
}

def extract_decimal(price: float) -> int:
    try:
        if pd.isna(price) or price is None:
            return -1
        return int(f"{float(price):.2f}".split(".")[1])
    except Exception:
        return -1

def get_circular_midpoint(d1: int, d2: int) -> int:
    diff = (d2 - d1) % 100
    if diff <= 50:
        return (d1 + diff // 2) % 100
    else:
        diff_rev = (d1 - d2) % 100
        return (d2 + diff_rev // 2) % 100

def generate_15_number_clusters(ltp_dec: int, vwap_dec: int) -> list:
    """Taiwan, KOSPI, Sensex: 5 Anchors * 3 Numbers (±1 Cushion) = 15 Numbers"""
    anchors = set()
    
    # 1. LTP Core
    anchors.add(ltp_dec)
    
    # 2. VWAP Core
    anchors.add(vwap_dec)
    
    # 3. Gap Midpoint
    mid = get_circular_midpoint(ltp_dec, vwap_dec)
    anchors.add(mid)
    
    # 4. Momentum Lead & 5. Pullback
    if ltp_dec >= vwap_dec:
        anchors.add((ltp_dec + 11) % 100)  # Forward Lead
        anchors.add((vwap_dec - 9) % 100)   # Rebound Pull
    else:
        anchors.add((ltp_dec - 11) % 100)  # Downward Lead
        anchors.add((vwap_dec + 9) % 100)   # Upward Pull

    basket = set()
    for a in anchors:
        for k in [-1, 0, 1]:
            basket.add((a + k) % 100)
            
    # Pad symmetrically if overlaps reduce count below 15
    curr = sorted(list(basket))
    step = 2
    while len(curr) < 15:
        curr.append((ltp_dec + step) % 100)
        curr = sorted(list(set(curr)))
        if len(curr) >= 15:
            break
        curr.append((ltp_dec - step) % 100)
        curr = sorted(list(set(curr)))
        step += 1
        
    return sorted(list(curr))[:15]

def generate_30_number_bridge(ltp_dec: int, vwap_dec: int, target_size: int = 30) -> list:
    """Germany DAX: Continuous Bridge Model"""
    if ltp_dec == vwap_dec:
        half = target_size // 2
        return sorted(list({(ltp_dec + k) % 100 for k in range(-half, half + 1)}))
    
    dist_cw = (vwap_dec - ltp_dec) % 100
    dist_ccw = (ltp_dec - vwap_dec) % 100
    
    bridge = set()
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

def compute_engine_metrics(calc_df: pd.DataFrame, model_type: str):
    last_row = calc_df.iloc[-1]
    ltp = float(last_row["Close"])
    ltp_dec = extract_decimal(ltp)
    snap_time = calc_df.index[-1].strftime("%I:%M %p IST")
    
    win = calc_df.tail(15)
    typ = (win["High"] + win["Low"] + win["Close"]) / 3.0
    vol = win["Volume"] if "Volume" in win.columns else pd.Series(0, index=win.index)
    vwap = float((typ * vol).sum() / vol.sum()) if vol.sum() > 0 else float(typ.mean())
    vwap_dec = extract_decimal(vwap)
    
    if model_type == "cluster_15":
        basket = generate_15_number_clusters(ltp_dec, vwap_dec)
    else:
        basket = generate_30_number_bridge(ltp_dec, vwap_dec, target_size=30)
        
    return {
        "ltp": ltp,
        "ltp_dec": ltp_dec,
        "vwap": vwap,
        "vwap_dec": vwap_dec,
        "basket": basket,
        "time": snap_time,
        "model_label": "15-Number Sniper Cluster" if model_type == "cluster_15" else "30-Number Continuous Bridge"
    }

@st.cache_data(ttl=60)
def fetch_history(symbol: str):
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="5d", interval="5m")
    if df.empty or "Close" not in df.columns:
        return None
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(IST)
    else:
        df.index = df.index.tz_convert(IST)
    df["Date"] = df.index.date
    return df

st.title("🎯 Global Indices Decimal Engine (Hybrid Locked)")
st.caption("Taiwan / KOSPI / Sensex (15 Numbers) | Germany DAX (30 Numbers)")

now_ist = datetime.now(IST)
cur_date = now_ist.date()

st.sidebar.markdown(f"**Current IST:** `{now_ist.strftime('%Y-%m-%d %I:%M:%S %p')}`")
if st.sidebar.button("🔄 Sync Feed"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("🔒 Strict Lock Schedule")
for name, c in INDEX_REGISTRY.items():
    st.sidebar.write(f"• **{name.split()[0]}**: Locks `{c['lock_h']:02d}:{c['lock_m']:02d}` ({c['model']})")

cols = st.columns(2)

for i, (name, cfg) in enumerate(INDEX_REGISTRY.items()):
    col = cols[i % 2]
    with col:
        st.subheader(f"📊 {name}")
        lock_dt = IST.localize(datetime.combine(cur_date, time(cfg["lock_h"], cfg["lock_m"])))
        is_locked = now_ist >= lock_dt
        
        with st.spinner(f"Processing {name}..."):
            df_all = fetch_history(cfg["symbol"])
            
        if df_all is None:
            st.error("Data feed unavailable.")
            st.markdown("---")
            continue
            
        day_df = df_all[df_all["Date"] == cur_date].copy()
        if day_df.empty:
            latest_date = df_all["Date"].max()
            day_df = df_all[df_all["Date"] == latest_date].copy()
            lock_dt = IST.localize(datetime.combine(latest_date, time(cfg["lock_h"], cfg["lock_m"])))
            is_locked = True
            st.caption(f"Showing archived session: `{latest_date}`")

        # HARD LOCK: Once lock_dt passes, filter strictly up to lock_dt
        if is_locked:
            snap_df = day_df[day_df.index <= lock_dt]
            if snap_df.empty:
                snap_df = day_df.copy()
            res = compute_engine_metrics(snap_df, cfg["model"])
            st.success(f"🔒 **HARD-LOCKED (15m Pre-Close)** [Tick: {res['time']}]")
        else:
            res = compute_engine_metrics(day_df, cfg["model"])
            st.info(f"⏳ **LIVE UNTIL LOCK** (Will freeze at {cfg['lock_h']:02d}:{cfg['lock_m']:02d} IST)")

        m1, m2, m3 = st.columns(3)
        m1.metric("LTP at Lock", f"{res['ltp']:,.2f}", f".{res['ltp_dec']:02d}")
        m2.metric("VWAP at Lock", f"{res['vwap']:,.2f}", f".{res['vwap_dec']:02d}")
        m3.metric("Basket Count", f"{len(res['basket'])} Numbers", res["model_label"])

        st.markdown("**🎯 Predicted Decimal Basket:**")
        st.markdown(" ".join([f"`{n:02d}`" for n in res["basket"]]))
        st.markdown("---")
