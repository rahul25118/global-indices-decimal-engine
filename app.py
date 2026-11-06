"""
UNIFIED 4-INDEX CLOSING DECIMAL ENGINE - 100% PERSISTENT ACROSS BROWSER RELOADS
Taiwan & Sensex: 15m Pre-Close (Standard Dual-Band)
KOSPI & DAX: 30m Pre-Close (Compact Dynamic Prime 6-8 nos)
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import pytz
from datetime import datetime

st.set_page_config(
    page_title="4-Index Closing Decimal Engine",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="collapsed"
)

IST = pytz.timezone("Asia/Kolkata")
now_ist = datetime.now(IST)
today_str = now_ist.strftime("%Y-%m-%d")

INDICES = {
    "Taiwan (TAIEX)": {
        "symbol": "^TWII",
        "cutoff_hour": 10,
        "cutoff_min": 45,
        "cutoff_label": "10:45 AM IST (15m पहले)",
        "currency": "TWD",
        "engine_mode": "standard"
    },
    "India (BSE Sensex)": {
        "symbol": "^BSESN",
        "cutoff_hour": 15,
        "cutoff_min": 15,
        "cutoff_label": "03:15 PM IST (15m पहले)",
        "currency": "INR",
        "engine_mode": "standard"
    },
    "South Korea (KOSPI)": {
        "symbol": "^KS11",
        "cutoff_hour": 11,
        "cutoff_min": 30,
        "cutoff_label": "11:30 AM IST (30m पहले)",
        "currency": "KRW",
        "engine_mode": "compact_prime"
    },
    "Germany (DAX)": {
        "symbol": "^GDAXI",
        "cutoff_hour": 21,
        "cutoff_min": 30,
        "cutoff_label": "09:30 PM IST (30m पहले)",
        "currency": "EUR",
        "engine_mode": "compact_prime"
    }
}

def extract_dec(price: float) -> int:
    return int(f"{price:.2f}".split(".")[1])

def get_band(center_dec: int, half_size: int = 7) -> set:
    return {(center_dec + k) % 100 for k in range(-half_size, half_size + 1)}

def process_market_slice(filtered_df, engine_mode: str):
    target_row = filtered_df.iloc[-1]
    price = float(target_row["Close"])
    bar_time = filtered_df.index[-1].strftime("%I:%M %p IST")

    win = filtered_df.tail(15)
    typ_p = (win["High"] + win["Low"] + win["Close"]) / 3.0
    vol = win["Volume"]
    vwap = (typ_p * vol).sum() / vol.sum() if vol.sum() > 0 else typ_p.mean()

    dec_p = extract_dec(price)
    dec_v = extract_dec(vwap)

    band_p7 = get_band(dec_p, 7)
    band_v7 = get_band(dec_v, 7)

    if engine_mode == "compact_prime":
        # कोरिया और जर्मनी के लिए: ओवरलैप >= 4 होने पर वही, नहीं तो टाइट ±3 LTP कोर (6-8 नंबर्स)
        prime_overlap = band_p7.intersection(band_v7)
        if len(prime_overlap) >= 4:
            prime = prime_overlap
        else:
            prime = get_band(dec_p, 3)
        combined = band_p7.union(band_v7)
    else:
        # ताइवान और सेंसेक्स के लिए: पहले जैसा मूल डुअल-बैंड मॉडल
        prime = band_p7.intersection(band_v7)
        combined = band_p7.union(band_v7)

    return {
        "price": price,
        "dec_p": dec_p,
        "vwap": vwap,
        "dec_v": dec_v,
        "prime": sorted(list(prime)),
        "combined": sorted(list(combined)),
        "locked_bar_time": bar_time
    }

# स्थायी सर्वर-साइड हार्ड-लॉक (ttl=None)
@st.cache_data(ttl=None, show_spinner=False)
def get_locked_day_data(symbol: str, date_str: str, cut_h: int, cut_m: int, engine_mode: str):
    t = yf.Ticker(symbol)
    df = t.history(period="5d", interval="5m")
    if df.empty:
        return None

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(IST)
    else:
        df.index = df.index.tz_convert(IST)

    cutoff_limit = now_ist.replace(hour=cut_h, minute=cut_m, second=0, microsecond=0)
    filtered = df[df.index <= cutoff_limit]
    if filtered.empty:
        filtered = df

    return process_market_slice(filtered, engine_mode)

# कट-ऑफ से पहले का लाइव डेटा (15 सेकंड रीफ्रेश)
@st.cache_data(ttl=15, show_spinner=False)
def get_live_data(symbol: str, engine_mode: str):
    t = yf.Ticker(symbol)
    df = t.history(period="2d", interval="5m")
    if df.empty:
        return None

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(IST)
    else:
        df.index = df.index.tz_convert(IST)

    return process_market_slice(df, engine_mode)

st.title("🔒 4-इंडेक्स क्लोजिंग दशमलव इंजन (हाइब्रिड आर्किटेक्चर)")
st.caption("Taiwan (10:45 AM) • Sensex (03:15 PM) • KOSPI (11:30 AM) • DAX (09:30 PM IST)")

cols = st.columns(4)

for idx_i, (name, meta) in enumerate(INDICES.items()):
    with cols[idx_i]:
        st.subheader(name)
        st.caption(f"कट-ऑफ विंडो: **{meta['cutoff_label']}**")

        cut_h = meta["cutoff_hour"]
        cut_m = meta["cutoff_min"]
        is_locked = (now_ist.hour > cut_h) or (now_ist.hour == cut_h and now_ist.minute >= cut_m)

        if is_locked:
            res = get_locked_day_data(meta["symbol"], today_str, cut_h, cut_m, meta["engine_mode"])
            st.success(f"🔒 **डेटा स्थायी रूप से लॉक है**")
        else:
            res = get_live_data(meta["symbol"], meta["engine_mode"])
            st.warning("⏳ लाइव चल रहा है (कट-ऑफ पर लॉक होगा)")

        if not res:
            st.error("डेटा लोड नहीं हो सका।")
            continue

        st.metric(
            label=f"भाव ({meta['currency']})",
            value=f"{res['price']:,.2f}",
            delta=f"दशमलव: .{res['dec_p']:02d}"
        )
        st.write(f"• इंडिकेटिव VWAP: **.{res['dec_v']:02d}** ({res['vwap']:,.2f})")
        st.caption(f"🔒 लॉक्ड टिक समय: `{res['locked_bar_time']}`")

        # प्राइम कोर डिस्प्ले
        if meta["engine_mode"] == "compact_prime":
            st.markdown(f"**🔥 टाइट डायनामिक प्राइम ({len(res['prime'])} nos):**")
        else:
            st.markdown(f"**🔥 प्राइम कोर ({len(res['prime'])} nos):**")

        if res["prime"]:
            st.markdown(" ".join([f"` .{x:02d} `" for x in res["prime"]]))
        else:
            st.caption("कोई प्राइम ओवरलैप नहीं")

        # पूर्ण बास्केट डिस्प्ले
        st.markdown(f"**📋 पूर्ण बास्केट ({len(res['combined'])} नंबर्स):**")
        st.markdown(" ".join([
            f"<span style='background-color:#1e293b;color:#38bdf8;padding:4px 8px;border-radius:4px;font-weight:bold;margin:2px;display:inline-block;'>.{x:02d}</span>"
            for x in res["combined"]
        ]), unsafe_allow_html=True)
