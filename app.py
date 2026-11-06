"""
GLOBAL INDICES DECIMAL ENGINE (15-MINUTE PRE-CLOSE FREEZE)
Pure Dual-Band Basket (±7 LTP ∪ ±7 VWAP -> ~28-30 Numbers)
Server-side persistent locking at t-15m before official close.
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, time, date
import pytz

st.set_page_config(
    page_title="Global Indices Decimal Engine",
    page_icon="🎯",
    layout="wide"
)

IST = pytz.timezone("Asia/Kolkata")

INDEX_REGISTRY = {
    "Taiwan (TAIEX)": {
        "symbol": "^TWII",
        "close_h": 11, "close_m": 0,
        "lock_h": 10,  "lock_m": 45,
        "open_h": 6,   "open_m": 30
    },
    "South Korea (KOSPI)": {
        "symbol": "^KS11",
        "close_h": 12, "close_m": 0,
        "lock_h": 11,  "lock_m": 45,
        "open_h": 5,   "open_m": 30
    },
    "India (BSE Sensex)": {
        "symbol": "^BSESN",
        "close_h": 15, "close_m": 30,
        "lock_h": 15,  "lock_m": 15,
        "open_h": 9,   "open_m": 15
    },
    "Germany (DAX)": {
        "symbol": "^GDAXI",
        "close_h": 22, "close_m": 0,
        "lock_h": 21,  "lock_m": 45,
        "open_h": 13,  "open_m": 30
    }
}

def extract_decimal(price: float) -> int:
    try:
        if pd.isna(price) or price is None:
            return -1
        return int(f"{float(price):.2f}".split(".")[1])
    except Exception:
        return -1

def get_dual_band_numbers(ltp_dec: int, vwap_dec: int, half_size: int = 7) -> list:
    ltp_band = {(ltp_dec + k) % 100 for k in range(-half_size, half_size + 1)}
    vwap_band = {(vwap_dec + k) % 100 for k in range(-half_size, half_size + 1)}
    return sorted(list(ltp_band.union(vwap_band)))

@st.cache_data(ttl=None)
def get_locked_prediction_for_day(index_name: str, lock_date: date):
    cfg = INDEX_REGISTRY[index_name]
    ticker = yf.Ticker(cfg["symbol"])
    df = ticker.history(period="5d", interval="5m")

    if df.empty or "Close" not in df.columns:
        return None

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(IST)
    else:
        df.index = df.index.tz_convert(IST)

    df["Date"] = df.index.date
    day_df = df[df["Date"] == lock_date].copy()

    if day_df.empty:
        return None

    lock_datetime = IST.localize(datetime.combine(lock_date, time(cfg["lock_h"], cfg["lock_m"])))
    snap_df = day_df[day_df.index <= lock_datetime]

    if snap_df.empty:
        return None

    last_row = snap_df.iloc[-1]
    snap_ltp = float(last_row["Close"])
    ltp_dec = extract_decimal(snap_ltp)
    snap_time = snap_df.index[-1].strftime("%I:%M %p IST")

    win = snap_df.tail(15)
    typ = (win["High"] + win["Low"] + win["Close"]) / 3.0
    vol = win["Volume"]
    snap_vwap = (typ * vol).sum() / vol.sum() if vol.sum() > 0 else typ.mean()
    vwap_dec = extract_decimal(snap_vwap)

    basket = get_dual_band_numbers(ltp_dec, vwap_dec, half_size=7)

    return {
        "status": "LOCKED",
        "lock_time": snap_time,
        "ltp": snap_ltp,
        "ltp_dec": ltp_dec,
        "vwap": snap_vwap,
        "vwap_dec": vwap_dec,
        "basket": basket,
        "basket_size": len(basket)
    }

def get_live_provisional_snapshot(index_name: str):
    cfg = INDEX_REGISTRY[index_name]
    ticker = yf.Ticker(cfg["symbol"])
    df = ticker.history(period="1d", interval="5m")

    if df.empty or "Close" not in df.columns:
        return None

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(IST)
    else:
        df.index = df.index.tz_convert(IST)

    last_row = df.iloc[-1]
    curr_ltp = float(last_row["Close"])
    ltp_dec = extract_decimal(curr_ltp)
    curr_time = df.index[-1].strftime("%I:%M %p IST")

    win = df.tail(15)
    typ = (win["High"] + win["Low"] + win["Close"]) / 3.0
    vol = win["Volume"]
    curr_vwap = (typ * vol).sum() / vol.sum() if vol.sum() > 0 else typ.mean()
    vwap_dec = extract_decimal(curr_vwap)

    basket = get_dual_band_numbers(ltp_dec, vwap_dec, half_size=7)

    return {
        "status": "LIVE_PROVISIONAL",
        "time": curr_time,
        "ltp": curr_ltp,
        "ltp_dec": ltp_dec,
        "vwap": curr_vwap,
        "vwap_dec": vwap_dec,
        "basket": basket,
        "basket_size": len(basket)
    }

st.title("🎯 Global Indices Decimal Engine")
st.caption("Standard Dual-Band Model (±7 LTP ∪ ±7 VWAP) | 15-Minute Pre-Close Permanent Lock")

now_ist = datetime.now(IST)
current_date = now_ist.date()

st.sidebar.markdown(f"**Current IST:** `{now_ist.strftime('%Y-%m-%d %I:%M:%S %p')}`")
if st.sidebar.button("🔄 Check / Refresh Market Data"):
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("📌 15-Minute Lock Schedule")
for name, c in INDEX_REGISTRY.items():
    st.sidebar.write(f"• **{name.split()[0]}**: Lock at `{c['lock_h']:02d}:{c['lock_m']:02d} IST` (Close `{c['close_h']:02d}:{c['close_m']:02d}`)")

cols = st.columns(2)

for i, (name, cfg) in enumerate(INDEX_REGISTRY.items()):
    col = cols[i % 2]
    with col:
        st.subheader(f"📊 {name}")
        lock_dt = IST.localize(datetime.combine(current_date, time(cfg["lock_h"], cfg["lock_m"])))
        is_locked = now_ist >= lock_dt

        with st.spinner(f"Fetching {name}..."):
            if is_locked:
                data = get_locked_prediction_for_day(name, current_date)
            else:
                data = get_live_provisional_snapshot(name)

        if not data:
            st.warning("Awaiting market data feed...")
            st.markdown("---")
            continue

        if data["status"] == "LOCKED":
            st.success(f"🔒 **PERMANENTLY LOCKED** at {data['lock_time']}")
        else:
            st.info(f"⏳ **RUNNING LIVE** (Will lock at {cfg['lock_h']:02d}:{cfg['lock_m']:02d} IST)")

        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric("Snapshot LTP", f"{data['ltp']:,.2f}", f"Dec: .{data['ltp_dec']:02d}")
        m_col2.metric("Snapshot VWAP", f"{data['vwap']:,.2f}", f"Dec: .{data['vwap_dec']:02d}")
        m_col3.metric("Total Basket", f"{data['basket_size']} Numbers")

        st.markdown("**🎯 Predicted Closing Decimal Basket:**")
        formatted_numbers = " ".join([f"`{n:02d}`" for n in data["basket"]])
        st.markdown(formatted_numbers)
        st.markdown("---")
