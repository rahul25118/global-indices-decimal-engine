"""
GLOBAL TRIO CLOSING DECIMAL ENGINE - 100% HARD-LOCKED AT CUTOFF
Taiwan: Hard freeze at 10:45 AM IST
South Korea: Hard freeze at 11:45 AM IST
Germany: Hard freeze at 09:45 PM IST
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import pytz
from datetime import datetime, time

st.set_page_config(
    page_title="Global 15-Min Decimal Engine (Locked)",
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

def extract_dec(price: float) -> int:
    return int(f"{price:.2f}".split(".")[1])

def get_band(center_dec: int, half_size: int = 7) -> set:
    return {(center_dec + k) % 100 for k in range(-half_size, half_size + 1)}

def fetch_locked_data(meta: dict):
    cut_h = meta["cutoff_hour"]
    cut_m = meta["cutoff_min"]
    cutoff_time_today = datetime.combine(today_date, time(cut_h, cut_m))
    cutoff_dt = IST.localize(cutoff_time_today)

    # क्या कट-ऑफ समय बीत चुका है?
    is_locked = now_ist >= cutoff_dt

    sym = meta["symbol"]
    t = yf.Ticker(sym)
    
    # 5 दिन का 5m डेटा ताकि टाइमस्टैम्प पूरी तरह उपलब्ध रहे
    df = t.history(period="5d", interval="5m")
    if df.empty:
        return None, is_locked

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(IST)
    else:
        df.index = df.index.tz_convert(IST)

    # अगर कट-ऑफ हो चुका है -> सिर्फ कट-ऑफ टाइमस्टैम्प या उससे पहले की कैंडल्स ही फिल्टर होंगी
    if is_locked:
        valid_df = df[df.index <= cutoff_dt]
    else:
        valid_df = df

    if valid_df.empty:
        valid_df = df

    # कट-ऑफ वाले मिनट की अंतिम कैंडल
    target_row = valid_df.iloc[-1]
    locked_price = float(target_row["Close"])
    locked_time_str = valid_df.index[-1].strftime("%I:%M %p IST")

    # अंतिम 15 बार्स का VWAP
    win = valid_df.tail(15)
    typ_p = (win["High"] + win["Low"] + win["Close"]) / 3.0
    vol = win["Volume"]
    locked_vwap = (typ_p * vol).sum() / vol.sum() if vol.sum() > 0 else typ_p.mean()

    dec_p = extract_dec(locked_price)
    dec_v = extract_dec(locked_vwap)
    band_p = get_band(dec_p, 7)
    band_v = get_band(dec_v, 7)

    return {
        "price": locked_price,
        "dec_p": dec_p,
        "vwap": locked_vwap,
        "dec_v": dec_v,
        "combined": sorted(list(band_p.union(band_v))),
        "prime": sorted(list(band_p.intersection(band_v))),
        "locked_bar_time": locked_time_str
    }, is_locked

st.title("🔒 ग्लोबल इंडेक्स 15-मिनट कट-ऑफ हार्ड-लॉक इंजन")
st.caption("ताइवान (10:45 AM), दक्षिण कोरिया (11:45 AM), जर्मनी (09:45 PM IST)")

if st.sidebar.button("🔄 तुरंत रिफ्रेश करें"):
    st.cache_data.clear()
    st.rerun()

cols = st.columns(3)

for idx_i, (name, meta) in enumerate(INDICES.items()):
    with cols[idx_i]:
        st.subheader(name)
        st.caption(f"कट-ऑफ विंडो: **{meta['cutoff_label']}**")

        res, locked = fetch_locked_data(meta)

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
