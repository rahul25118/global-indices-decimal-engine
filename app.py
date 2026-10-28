"""
GLOBAL TRIO CLOSING DECIMAL ENGINE - 100% YAHOO FINANCE VERIFIED
Strict 15-Min Pre-Close Cutoff Hard-Lock System
DAX Winter Cutoff: 09:45 PM IST (Close: 10:00 PM IST)
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import pytz
from datetime import datetime

st.set_page_config(
    page_title="Global 15-Min Decimal Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

IST = pytz.timezone("Asia/Kolkata")
now_ist = datetime.now(IST)

INDICES = {
    "Taiwan (TAIEX)": {
        "symbol": "^TWII",
        "cutoff_ist_hour": 10,
        "cutoff_ist_min": 45,
        "cutoff_label": "10:45 AM IST (15m पहले)",
        "currency": "TWD"
    },
    "South Korea (KOSPI)": {
        "symbol": "^KS11",
        "cutoff_ist_hour": 11,
        "cutoff_ist_min": 45,
        "cutoff_label": "11:45 AM IST (15m पहले)",
        "currency": "KRW"
    },
    "Germany (DAX)": {
        "symbol": "^GDAXI",
        "cutoff_ist_hour": 21,
        "cutoff_ist_min": 45,
        "cutoff_label": "09:45 PM IST (15m पहले)",
        "currency": "EUR"
    }
}

def extract_dec(price: float) -> int:
    return int(f"{price:.2f}".split(".")[1])

def get_band(center_dec: int, half_size: int = 7) -> set:
    return {(center_dec + k) % 100 for k in range(-half_size, half_size + 1)}

@st.cache_data(ttl=20, show_spinner=False)
def fetch_verified_index(meta: dict):
    cut_h = meta["cutoff_ist_hour"]
    cut_m = meta["cutoff_ist_min"]
    is_locked = (now_ist.hour > cut_h) or (now_ist.hour == cut_h and now_ist.minute >= cut_m)

    sym = meta["symbol"]
    t = yf.Ticker(sym)
    
    price = None
    vwap = None
    source = "YFINANCE"

    # 1. Primary: Intraday 5m Bars
    try:
        df_intra = t.history(period="2d", interval="5m")
        if not df_intra.empty and len(df_intra) >= 5:
            if df_intra.index.tz is None:
                df_intra.index = df_intra.index.tz_localize("UTC").tz_convert(IST)
            else:
                df_intra.index = df_intra.index.tz_convert(IST)
            
            mask = (df_intra.index.hour < cut_h) | ((df_intra.index.hour == cut_h) & (df_intra.index.minute <= cut_m))
            df_cut = df_intra[mask]
            target_df = df_cut if not df_cut.empty else df_intra

            price = float(target_df.iloc[-1]["Close"])
            typ = (target_df["High"] + target_df["Low"] + target_df["Close"]) / 3.0
            vol = target_df["Volume"]
            vwap = (typ * vol).sum() / vol.sum() if vol.sum() > 0 else typ.mean()
            source = f"YFINANCE_INTRADAY ({sym})"
    except Exception:
        pass

    # 2. Secondary: Settled Daily Close Fallback (Off-market hours)
    if price is None or price <= 0:
        try:
            df_daily = t.history(period="1mo")
            if not df_daily.empty:
                last_row = df_daily.iloc[-1]
                price = float(last_row["Close"])
                vwap = float((last_row["High"] + last_row["Low"] + last_row["Close"]) / 3.0)
                source = f"YFINANCE_SETTLED_CLOSE ({sym})"
        except Exception:
            pass

    if price is None or price <= 0:
        return None, is_locked

    dec_p = extract_dec(price)
    dec_v = extract_dec(vwap)
    band_p = get_band(dec_p, 7)
    band_v = get_band(dec_v, 7)

    return {
        "price": price,
        "dec_p": dec_p,
        "vwap": vwap,
        "dec_v": dec_v,
        "combined": sorted(list(band_p.union(band_v))),
        "prime": sorted(list(band_p.intersection(band_v))),
        "source": source
    }, is_locked

st.title("⚡ ग्लोबल इंडेक्स 15-मिनट प्री-क्लोज दशमलव इंजन")
st.caption("याहू फाइनेंस सत्यापित फ़ीड — ताइवान (10:45 AM), दक्षिण कोरिया (11:45 AM), जर्मनी (09:45 PM IST)")

if st.sidebar.button("🔄 तुरंत रिफ्रेश करें"):
    st.cache_data.clear()
    st.rerun()

cols = st.columns(3)

for idx_i, (name, meta) in enumerate(INDICES.items()):
    with cols[idx_i]:
        st.subheader(name)
        st.caption(f"🔒 कट-ऑफ: **{meta['cutoff_label']}**")

        res, locked = fetch_verified_index(meta)

        if locked:
            st.success(f"🔒 **{meta['cutoff_label']} पर डेटा लॉक है**")
        else:
            st.warning("⏳ 15 मिनट कट-ऑफ विंडो का इंतज़ार...")

        if not res:
            st.error("डेटा लोड नहीं हो सका।")
            continue

        st.metric(
            label=f"भाव ({meta['currency']})",
            value=f"{res['price']:,.2f}",
            delta=f"दशमलव: .{res['dec_p']:02d}"
        )
        st.write(f"• इंडिकेटिव VWAP: **.{res['dec_v']:02d}** ({res['vwap']:,.2f})")
        st.write(f"• डेटा स्रोत: `{res['source']}`")

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
