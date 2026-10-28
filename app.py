"""
GLOBAL TRIO CLOSING DECIMAL ENGINE
- South Korea: KOSPI (^KS11)
- Germany: DAX (^GDAXI)
- Taiwan: TAIEX (^TWII)

Dual Data Pipeline: Google Finance (Live Primary) + Yahoo Finance (Historical & Fallback)
Model: VWAP (+/-7) + Price (+/-7) -> ~15-28 tightly clustered numbers per index.
"""

import streamlit as st
import pandas as pd
import numpy as np
import requests
import re
import json
import yfinance as yf
import pytz
from datetime import datetime

st.set_page_config(
    page_title="Global Trio Decimal Engine",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------------------------------------
# TIMEZONE & INDEX DEFINITIONS
# -------------------------------------------------------------
INDICES = {
    "Taiwan (TAIEX)": {
        "symbol_yf": "^TWII",
        "symbol_gf": "TPE:TAIEX",
        "timezone": "Asia/Taipei",
        "close_local": "13:30",
        "close_ist": "11:00 AM IST",
        "currency": "TWD",
        "desc": "Taiwan Stock Exchange Capitalization Weighted Stock Index"
    },
    "South Korea (KOSPI)": {
        "symbol_yf": "^KS11",
        "symbol_gf": "KRX:KOSPI",
        "timezone": "Asia/Seoul",
        "close_local": "15:30",
        "close_ist": "12:00 PM IST",
        "currency": "KRW",
        "desc": "Korea Composite Stock Price Index"
    },
    "Germany (DAX)": {
        "symbol_yf": "^GDAXI",
        "symbol_gf": "INDEXDB:DAX",
        "timezone": "Europe/Berlin",
        "close_local": "17:30",
        "close_ist": "10:00 PM IST",
        "currency": "EUR",
        "desc": "Deutscher Aktienindex (DAX 40)"
    }
}

# -------------------------------------------------------------
# MODEL FUNCTIONS (STRICTLY UNCHANGED)
# -------------------------------------------------------------
def extract_dec(price: float) -> int:
    return int(f"{price:.2f}".split(".")[1])

def get_band(center_dec: int, half_size: int = 7) -> set:
    return {(center_dec + k) % 100 for k in range(-half_size, half_size + 1)}

# -------------------------------------------------------------
# DUAL DATA PIPELINE (GOOGLE FINANCE + YAHOO FINANCE)
# -------------------------------------------------------------
@st.cache_data(ttl=15, show_spinner=False)
def fetch_dual_stream_data(sym_yf: str, sym_gf: str, tz_name: str):
    """
    Combines Google Finance (Ultra-Fast Live Ticks) with
    Yahoo Finance (Full Intraday Structure & Historical Bar Baseline).
    """
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }

    live_gf_price = None
    # 1. Fast Live Scraping from Google Finance
    try:
        url_gf = f"https://www.google.com/finance/quote/{sym_gf}"
        resp_gf = requests.get(url_gf, headers=req_headers, timeout=4)
        if resp_gf.status_code == 200:
            m = re.search(r'data-last-price="([0-9.,]+)"', resp_gf.text)
            if m:
                live_gf_price = float(m.group(1).replace(",", ""))
    except Exception:
        pass

    # 2. Yahoo Finance Intraday Feed
    df_yf = pd.DataFrame()
    try:
        t = yf.Ticker(sym_yf)
        df_yf = t.history(period="1d", interval="1m")
        if df_yf.empty or len(df_yf) < 5:
            df_yf = t.history(period="5d", interval="1m")
    except Exception:
        pass

    target_tz = pytz.timezone(tz_name)

    if not df_yf.empty:
        if df_yf.index.tz is None:
            df_yf.index = df_yf.index.tz_localize("UTC").tz_convert(target_tz)
        else:
            df_yf.index = df_yf.index.tz_convert(target_tz)
        
        last_date = df_yf.index[-1].date()
        df_session = df_yf[df_yf.index.date == last_date].copy()
        df_session["Time"] = df_session.index.strftime("%H:%M")

        # Fusion: If Google Finance price is available and fresher, append/calibrate latest bar
        if live_gf_price is not None and live_gf_price > 0:
            last_yf_price = float(df_session.iloc[-1]["Close"])
            # If Google Finance has updated tick
            if abs(live_gf_price - last_yf_price) > 0.001:
                cur_local_time = datetime.now(target_tz).strftime("%H:%M")
                new_row = pd.DataFrame([{
                    "Open": live_gf_price,
                    "High": live_gf_price,
                    "Low": live_gf_price,
                    "Close": live_gf_price,
                    "Volume": 1.0,
                    "Time": cur_local_time
                }], index=[datetime.now(target_tz)])
                df_session = pd.concat([df_session, new_row])
                return df_session, "DUAL_FUSION (Google Live + YF Historical)"

        return df_session, "YFINANCE_BACKUP"

    # 3. Emergency Single Tick fallback from Google Finance
    if live_gf_price is not None:
        cur_local_time = datetime.now(target_tz).strftime("%H:%M")
        df_single = pd.DataFrame([{
            "Open": live_gf_price,
            "High": live_gf_price,
            "Low": live_gf_price,
            "Close": live_gf_price,
            "Volume": 1.0,
            "Time": cur_local_time
        }], index=[datetime.now(target_tz)])
        return df_single, "GOOGLE_FINANCE_LIVE"

    return None, "डेटा उपलब्ध नहीं है"

def compute_index_model(df_session):
    if df_session is None or df_session.empty:
        return None

    last_bar = df_session.iloc[-1]
    p_last = float(last_bar["Close"])
    dec_p = extract_dec(p_last)
    timestamp_last = df_session.index[-1]

    # Pre-close VWAP calculation (last 20 bars or window)
    window = df_session.tail(20)
    typ_p = (window["High"] + window["Low"] + window["Close"]) / 3.0
    vol = window["Volume"]
    calc_vwap = (typ_p * vol).sum() / vol.sum() if vol.sum() > 0 else typ_p.mean()
    dec_vwap = extract_dec(calc_vwap)

    band_p = get_band(dec_p, 7)
    band_v = get_band(dec_vwap, 7)

    combined_basket = sorted(list(band_p.union(band_v)))
    prime_core = sorted(list(band_p.intersection(band_v)))

    return {
        "price": p_last,
        "dec_price": dec_p,
        "vwap": calc_vwap,
        "dec_vwap": dec_vwap,
        "combined": combined_basket,
        "prime": prime_core,
        "timestamp": timestamp_last
    }

# -------------------------------------------------------------
# APP INTERFACE
# -------------------------------------------------------------
st.title("🌐 ग्लोबल इंडेक्स क्लोजिंग दशमलव इंजन")
st.caption("ताइवान (TAIEX), दक्षिण कोरिया (KOSPI), और जर्मनी (DAX) — डुअल गूगल फाइनेंस + याहू लाइव इंजन")

st.sidebar.header("⚙️ कंट्रोल पैनल")
if st.sidebar.button("🔄 तुरंत रिफ्रेश करें"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.info("""
**सटीकता वास्तुकला:**
• **डेटा फ़ीड:** Google Finance (रियल-टाइम टिक) + Yahoo Finance (स्ट्रक्चर्ड हिस्ट्री)
• **बैंड:** VWAP (±7) + Price (±7)
• **औसत साइज़:** 15 से 28 नंबर्स प्रति इंडेक्स (हाई स्ट्राइक रेट)
""")

cols = st.columns(3)

for idx_i, (name, meta) in enumerate(INDICES.items()):
    with cols[idx_i]:
        st.subheader(name)
        st.caption(f"🕒 स्थानीय क्लोज: **{meta['close_local']}** | IST: **{meta['close_ist']}**")

        df_data, src = fetch_dual_stream_data(meta["symbol_yf"], meta["symbol_gf"], meta["timezone"])
        if df_data is None:
            st.error(f"डेटा लोड नहीं हो सका: {src}")
            continue

        res = compute_index_model(df_data)

        st.metric(
            label=f"अंतिम भाव ({meta['currency']})",
            value=f"{res['price']:,.2f}",
            delta=f"दशमलव: .{res['dec_price']:02d}"
        )
        st.write(f"• VWAP: **.{res['dec_vwap']:02d}** ({res['vwap']:,.2f})")
        st.write(f"• डेटा स्रोत: `{src}`")

        st.markdown(f"**🔥 प्राइम कोर ({len(res['prime'])} nos):**")
        if res["prime"]:
            chips_prime = " ".join([
                f"<span style='background-color:#0f172a;color:#f59e0b;padding:4px 8px;border-radius:4px;font-weight:bold;margin:2px;display:inline-block;'>.{x:02d}</span>"
                for x in res["prime"]
            ])
            st.markdown(chips_prime, unsafe_allow_html=True)
        else:
            st.caption("कोई ओवरलैप नहीं")

        st.markdown(f"**📋 पूर्ण बास्केट ({len(res['combined'])} नंबर्स):**")
        chips_all = " ".join([
            f"<span style='background-color:#1e293b;color:#38bdf8;padding:4px 8px;border-radius:4px;font-weight:bold;margin:2px;display:inline-block;'>.{x:02d}</span>"
            for x in res["combined"]
        ])
        st.markdown(chips_all, unsafe_allow_html=True)
        st.caption(f"समय टिक: {res['timestamp'].strftime('%H:%M:%S')}")
