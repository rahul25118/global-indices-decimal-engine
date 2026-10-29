"""
GLOBAL TRIO CLOSING DECIMAL ENGINE - ABSOLUTE SESSION-STATE HARD-LOCK
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import pytz
from datetime import datetime, time

st.set_page_config(
    page_title="Global 15-Min Decimal Engine (Permanent Lock)",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded"
)

IST = pytz.timezone("Asia/Kolkata")
now_ist = datetime.now(IST)
today_date = now_ist.date()

INDICES = {
    "Taiwan (TAIEX)": {
        "symbol": "^TWII",
        "cutoff_hour": 10,
        "cutoff_min": 45,
        "cutoff_label": "10:45 AM IST",
        "currency": "TWD"
    },
    "South Korea (KOSPI)": {
        "symbol": "^KS11",
        "cutoff_hour": 11,
        "cutoff_min": 45,
        "cutoff_label": "11:45 AM IST",
        "currency": "KRW"
    },
    "Germany (DAX)": {
        "symbol": "^GDAXI",
        "cutoff_hour": 21,
        "cutoff_min": 45,
        "cutoff_label": "09:45 PM IST",
        "currency": "EUR"
    }
}

# Session State Dictionary initialize karein permanent locking ke liye
if "locked_records" not in st.session_state:
    st.session_state.locked_records = {}

def extract_dec(price: float) -> int:
    return int(f"{price:.2f}".split(".")[1])

def get_band(center_dec: int, half_size: int = 7) -> set:
    return {(center_dec + k) % 100 for k in range(-half_size, half_size + 1)}

def get_market_data(name: str, meta: dict):
    cut_h = meta["cutoff_hour"]
    cut_m = meta["cutoff_min"]
    
    # Check karein kya cut-off time guzar chuka hai
    is_time_up = (now_ist.hour > cut_h) or (now_ist.hour == cut_h and now_ist.minute >= cut_m)

    # RULE 1: Agar cut-off ho chuka hai aur memory mein pehle se lock hai, wahi exact data return karo (Zero Re-calculation)
    if is_time_up and name in st.session_state.locked_records:
        return st.session_state.locked_records[name], True

    # RULE 2: Data fetch karo
    sym = meta["symbol"]
    t = yf.Ticker(sym)
    df = t.history(period="5d", interval="5m")

    if df.empty:
        # Fallback daily agar 5m na mile
        df_daily = t.history(period="5d")
        if df_daily.empty:
            return None, is_time_up
        last_row = df_daily.iloc[-1]
        p = float(last_row["Close"])
        v = float((last_row["High"] + last_row["Low"] + last_row["Close"]) / 3.0)
        lock_str = "Daily Close Fallback"
    else:
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)

        if is_time_up:
            # Cut-off time tak strictly filter karo
            cutoff_dt = IST.localize(datetime.combine(today_date, time(cut_h, cut_m)))
            df_filtered = df[df.index <= cutoff_dt]
            valid_df = df_filtered if not df_filtered.empty else df
        else:
            valid_df = df

        target_row = valid_df.iloc[-1]
        p = float(target_row["Close"])
        lock_str = valid_df.index[-1].strftime("%I:%M %p IST")

        # Indicative VWAP calculation (last 15 bars)
        win = valid_df.tail(15)
        typ_p = (win["High"] + win["Low"] + win["Close"]) / 3.0
        vol = win["Volume"]
        v = (typ_p * vol).sum() / vol.sum() if vol.sum() > 0 else typ_p.mean()

    dec_p = extract_dec(p)
    dec_v = extract_dec(v)
    band_p = get_band(dec_p, 7)
    band_v = get_band(dec_v, 7)

    record = {
        "price": p,
        "dec_p": dec_p,
        "vwap": v,
        "dec_v": dec_v,
        "combined": sorted(list(band_p.union(band_v))),
        "prime": sorted(list(band_p.intersection(band_v))),
        "locked_bar_time": lock_str
    }

    # RULE 3: Agar cut-off time ho chuka hai, toh record ko session_state mein hamesha ke liye daal do
    if is_time_up:
        st.session_state.locked_records[name] = record

    return record, is_time_up

st.title("🔒 ग्लोबल इंडेक्स 15-मिनट कट-ऑफ परमानेंट लॉक इंजन")
st.caption("ताइवान (10:45 AM), दक्षिण कोरिया (11:45 AM), जर्मनी (09:45 PM IST)")

# Sidebar refresh button: Yeh cache ko clear karega par locked session ko nahi chhedega
if st.sidebar.button("🔄 तुरंत रिफ्रेश करें"):
    st.rerun()

cols = st.columns(3)

for idx_i, (name, meta) in enumerate(INDICES.items()):
    with cols[idx_i]:
        st.subheader(name)
        st.caption(f"कट-ऑफ समय: **{meta['cutoff_label']}**")

        res, locked = get_market_data(name, meta)

        if locked:
            st.success(f"🔒 **डेटा स्थायी रूप से लॉक है ({meta['cutoff_label']})**")
        else:
            st.warning(f"⏳ लाइव चल रहा है (कट-ऑफ {meta['cutoff_label']} पर लॉक होगा)")

        if not res:
            st.error("डेटा लोड नहीं हो सका।")
            continue

        st.metric(
            label=f"भाव ({meta['currency']})",
            value=f"{res['price']:,.2f}",
            delta=f"दशमलव: .{res['dec_p']:02d}"
        )
        st.write(f"• इंडिकेटिव VWAP: **.{res['dec_v']:02d}** ({res['vwap']:,.2f})")
        st.caption(f"अंतिम लॉक टिक: `{res['locked_bar_time']}`")

        st.markdown(f"**🔥 प्राइम कोर ({len(res['prime'])} nos):**")
        if res["prime"]:
            st.markdown(" ".join([f"` .{x:02d} `" for x in res["prime"]]))
        else:
            st.caption("कोई प्राइम ओवरलैप नहीं")

        st.markdown(f"**📋 पूर्ण बास्केट ({len(res['combined'])} नंबर्स):**")
        st.markdown(" ".join([
            f"<span style='background-color:#1e293b;color:#38bdf8;padding:4px 8px;border-radius:4px;font-weight:bold;margin:2px;display:inline-block;'>.{x:02d}</span>"
            for x in res["combined"]
        ]), unsafe_allow_html=True)
