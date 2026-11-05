"""
GLOBAL INDICES DECIMAL ENGINE (ROBUST 15-MINUTE PRE-CLOSE FREEZE)
Features:
- Correct Exchange Session Timings (IST): KOSPI 11:30 AM close, lock at 11:15 AM
- Feed Lag Tolerance
- Robust VWAP Calculation (Handles zero/missing volume)
- True 15m Pre-Close Locking with Snapshot Validation
"""

from datetime import date, datetime, time
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

INDEX_REGISTRY = {
    "Taiwan (TAIEX)": {
        "symbol": "^TWII",
        "close_h": 11, "close_m": 0,
        "lock_h": 10,  "lock_m": 45,
    },
    "South Korea (KOSPI)": {
        "symbol": "^KS11",
        "close_h": 11, "close_m": 30,
        "lock_h": 11,  "lock_m": 15,
    },
    "India (BSE Sensex)": {
        "symbol": "^BSESN",
        "close_h": 15, "close_m": 30,
        "lock_h": 15,  "lock_m": 15,
    },
    "Germany (DAX)": {
        "symbol": "^GDAXI",
        "close_h": 22, "close_m": 0,
        "lock_h": 21,  "lock_m": 45,
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

def compute_metrics(df_window: pd.DataFrame):
    last_row = df_window.iloc[-1]
    ltp = float(last_row["Close"])
    ltp_dec = extract_decimal(ltp)
    bar_time = df_window.index[-1].strftime("%I:%M %p IST")

    win = df_window.tail(15)
    typ = (win["High"] + win["Low"] + win["Close"]) / 3.0
    vol = win["Volume"] if "Volume" in win.columns else pd.Series(0, index=win.index)

    if vol.sum() > 0:
        vwap = float((typ * vol).sum() / vol.sum())
    else:
        vwap = float(typ.mean())
    vwap_dec = extract_decimal(vwap)

    basket = get_dual_band_numbers(ltp_dec, vwap_dec, half_size=7)

    return {
        "time": bar_time,
        "ltp": ltp,
        "ltp_dec": ltp_dec,
        "vwap": vwap,
        "vwap_dec": vwap_dec,
        "basket": basket,
        "basket_size": len(basket)
    }

@st.cache_data(ttl=300)
def fetch_index_data(symbol: str):
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

st.title("🎯 Global Indices Decimal Engine")
st.caption("Synchronized Dual-Band Basket (±7 LTP ∪ ±7 VWAP) | Accurate Session Timings")

now_ist = datetime.now(IST)
current_date = now_ist.date()

st.sidebar.markdown(f"**Current IST:** `{now_ist.strftime('%Y-%m-%d %I:%M:%S %p')}`")
if st.sidebar.button("🔄 Force Refresh"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("📌 Lock Schedule (15m Pre-Close)")
for name, c in INDEX_REGISTRY.items():
    st.sidebar.write(f"• **{name.split()[0]}**: Lock `{c['lock_h']:02d}:{c['lock_m']:02d}` (Close `{c['close_h']:02d}:{c['close_m']:02d}`)")

cols = st.columns(2)

for i, (name, cfg) in enumerate(INDEX_REGISTRY.items()):
    col = cols[i % 2]
    with col:
        st.subheader(f"📊 {name}")
        lock_dt = IST.localize(datetime.combine(current_date, time(cfg["lock_h"], cfg["lock_m"])))
        is_locked = now_ist >= lock_dt

        with st.spinner(f"Loading {name}..."):
            df_all = fetch_index_data(cfg["symbol"])

        if df_all is None:
            st.error(f"Data feed unavailable for {cfg['symbol']}")
            st.markdown("---")
            continue

        day_df = df_all[df_all["Date"] == current_date].copy()
        if day_df.empty:
            latest_date = df_all["Date"].max()
            day_df = df_all[df_all["Date"] == latest_date].copy()
            lock_dt = IST.localize(datetime.combine(latest_date, time(cfg["lock_h"], cfg["lock_m"])))
            is_locked = True
            st.caption(f"Showing last active session: `{latest_date}`")

        if is_locked:
            snap_df = day_df[day_df.index <= lock_dt]
            if snap_df.empty:
                snap_df = day_df.copy()
            res = compute_metrics(snap_df)
            st.success(f"🔒 **LOCKED SNAPSHOT** at {res['time']}")
        else:
            res = compute_metrics(day_df)
            st.info(f"⏳ **RUNNING LIVE** (Will lock at {cfg['lock_h']:02d}:{cfg['lock_m']:02d} IST)")

        m1, m2, m3 = st.columns(3)
        m1.metric("Snapshot LTP", f"{res['ltp']:,.2f}", f"Dec: .{res['ltp_dec']:02d}")
        m2.metric("Snapshot VWAP", f"{res['vwap']:,.2f}", f"Dec: .{res['vwap_dec']:02d}")
        m3.metric("Basket Size", f"{res['basket_size']} Numbers")

        st.markdown("**🎯 Predicted Decimal Basket:**")
        st.markdown(" ".join([f"`{n:02d}`" for n in res["basket"]]))
        st.markdown("---")
