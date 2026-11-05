"""
GLOBAL TRIO CLOSING DECIMAL ENGINE - ACCURATE TICKERS & DUAL FEED
- Taiwan: TAIEX (^TWII / TPE:TAIEX)
- South Korea: KOSPI (^KS11 / INDEXKRX:KOSPI)
- Germany: DAX (^GDAXI / INDEXDB:DAX)
"""

import streamlit as st
import pandas as pd
import numpy as np
import requests
import re
import yfinance as yf
import pytz
from datetime import datetime

st.set_page_config(
    page_title="Global Trio Decimal Engine",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded"
)

INDICES = {
    "Taiwan (TAIEX)": {
        "symbol_yf": "^TWII",
        "gf_url": "https://www.google.com/finance/quote/TPE:TAIEX",
        "timezone": "Asia/Taipei",
        "close_local": "13:30",
        "close_ist": "11:00 AM IST",
        "currency": "TWD"
    },
    "South Korea (KOSPI)": {
        "symbol_yf": "^KS11",
        "gf_url": "https://www.google.com/finance/quote/KOSPI:INDEXKRX",
        "timezone": "Asia/Seoul",
        "close_local": "15:30",
        "close_ist": "12:00 PM IST",
        "currency": "KRW"
    },
    "Germany (DAX)": {
        "symbol_yf": "^GDAXI",
        "gf_url": "https://www.google.com/finance/quote/DAX:INDEXDB",
        "timezone": "Europe/Berlin",
        "close_local": "17:30",
        "close_ist": "10:00 PM IST",
        "currency": "EUR"
    }
}

def extract_dec(price: float) -> int:
    return int(f"{price:.2f}".split(".")[1])

def get_band(center_dec: int, half_size: int = 7) -> set:
    return {(center_dec + k) % 100 for k in range(-half_size, half_size + 1)}

@st.cache_data(ttl=10, show_spinner=False)
def fetch_accurate_data(meta: dict):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }
    tz = pytz.timezone(meta["timezone"])

    live_gf_price = None
    # 1. Direct Live Google Finance
    try:
        r = requests.get(meta["gf_url"], headers=headers, timeout=4)
        if r.status_code == 200:
            m = re.search(r'data-last-price="([0-9.,]+)"', r.text)
            if not m:
                m = re.search(r'class="YMlKec fxKbKc">([0-9.,]+)<', r.text)
            if m:
                live_gf_price = float(m.group(1).replace(",", ""))
    except Exception:
        pass

    # 2. Yahoo Finance Data
    df_yf = pd.DataFrame()
    try:
        t = yf.Ticker(meta["symbol_yf"])
        df_yf = t.history(period="1d", interval="1m")
        if df_yf.empty or len(df_yf) < 5:
            df_yf = t.history(period="5d", interval="1m")
    except Exception:
        pass

    if not df_yf.empty:
        if df_yf.index.tz is None:
            df_yf.index = df_yf.index.tz_localize("UTC").tz_convert(tz)
        else:
            df_yf.index = df_yf.index.tz_convert(tz)

        last_date = df_yf.index[-1].date()
        df_day = df_yf[df_yf.index.date == last_date].copy()
        df_day["Time"] = df_day.index.strftime("%H:%M")

        if live_gf_price and live_gf_price > 0:
            last_p = float(df_day.iloc[-1]["Close"])
            if abs(live_gf_price - last_p) > 0.001:
                cur_t = datetime.now(tz).strftime("%H:%M")
                row = pd.DataFrame([{
                    "Open": live_gf_price,
                    "High": live_gf_price,
                    "Low": live_gf_price,
                    "Close": live_gf_price,
                    "Volume": 1.0,
                    "Time": cur_t
                }], index=[datetime.now(tz)])
                df_day = pd.concat([df_day, row])
                return df_day, "DUAL_FUSION (Google Live + YF Hist)"
        return df_day, "YFINANCE_BACKUP"

    if live_gf_price:
        cur_t = datetime.now(tz).strftime("%H:%M")
        df_single = pd.DataFrame([{
            "Open": live_gf_price,
            "High": live_gf_price,
            "Low": live_gf_price,
            "Close": live_gf_price,
            "Volume": 1.0,
            "Time": cur_t
        }], index=[datetime.now(tz)])
        return df_single, "GOOGLE_FINANCE_LIVE"

    return None, "डेटा उपलब्ध नहीं है"

def compute_model(df):
    p = float(df.iloc[-1]["Close"])
    dec_p = extract_dec(p)

    win = df.tail(20)
    typ_p = (win["High"] + win["Low"] + win["Close"]) / 3.0
    vol = win["Volume"]
    vwap = (typ_p * vol).sum() / vol.sum() if vol.sum() > 0 else typ_p.mean()
    dec_v = extract_dec(vwap)

    band_p = get_band(dec_p, 7)
    band_v = get_band(dec_v, 7)

    return {
        "price": p,
        "dec_p": dec_p,
        "vwap": vwap,
        "dec_v": dec_v,
        "combined": sorted(list(band_p.union(band_v))),
        "prime": sorted(list(band_p.intersection(band_v))),
        "timestamp": df.index[-1]
    }

st.title("🌐 ग्लोबल इंडेक्स क्लोजिंग दशमलव इंजन")
st.caption("सटीक रियल-टाइम इंडेक्स टिकर (TAIEX, KOSPI, DAX) — गूगल + याहू डुअल फ़ीड")

st.sidebar.header("⚙️ कंट्रोल पैनल")
if st.sidebar.button("🔄 तुरंत रिफ्रेश करें"):
    st.cache_data.clear()
    st.rerun()

cols = st.columns(3)

for idx_i, (name, meta) in enumerate(INDICES.items()):
    with cols[idx_i]:
        st.subheader(name)
        st.caption(f"🕒 स्थानीय क्लोज: **{meta['close_local']}** | IST: **{meta['close_ist']}**")

        df_data, src = fetch_accurate_data(meta)
        if df_data is None:
            st.error(f"डेटा लोड नहीं हो सका: {src}")
            continue

        res = compute_model(df_data)

        st.metric(
            label=f"अंतिम भाव ({meta['currency']})",
            value=f"{res['price']:,.2f}",
            delta=f"दशमलव: .{res['dec_p']:02d}"
        )
        st.write(f"• VWAP: **.{res['dec_v']:02d}** ({res['vwap']:,.2f})")
        st.write(f"• डेटा स्रोत: `{src}`")

        st.markdown(f"**🔥 प्राइम कोर ({len(res['prime'])} nos):**")
        if res["prime"]:
            st.markdown(" ".join([
                f"<span style='background-color:#0f172a;color:#f59e0b;padding:4px 8px;border-radius:4px;font-weight:bold;margin:2px;display:inline-block;'>.{x:02d}</span>"
                for x in res["prime"]
            ]), unsafe_allow_html=True)
        else:
            st.caption("कोई ओवरलैप नहीं")

        st.markdown(f"**📋 पूर्ण बास्केट ({len(res['combined'])} नंबर्स):**")
        st.markdown(" ".join([
            f"<span style='background-color:#1e293b;color:#38bdf8;padding:4px 8px;border-radius:4px;font-weight:bold;margin:2px;display:inline-block;'>.{x:02d}</span>"
            for x in res["combined"]
        ]), unsafe_allow_html=True)
        st.caption(f"समय टिक: {res['timestamp'].strftime('%H:%M:%S')}")
