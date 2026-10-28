"""
GLOBAL TRIO CLOSING DECIMAL ENGINE - ZERO-DELAY GOOGLE DIRECT
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
    page_title="Global 15-Min Decimal Engine (Google Live)",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

IST = pytz.timezone("Asia/Kolkata")
now_ist = datetime.now(IST)

INDICES = {
    "Taiwan (TAIEX)": {
        "symbol_yf": "^TWII",
        "search_queries": [
            "https://www.google.com/search?q=taiex+index+price&hl=en",
            "https://www.google.com/search?q=taiwan+weighted+index+google+finance&hl=en"
        ],
        "cutoff_ist_hour": 10,
        "cutoff_ist_min": 45,
        "cutoff_label": "10:45 AM IST (15m पहले)",
        "currency": "TWD"
    },
    "South Korea (KOSPI)": {
        "symbol_yf": "^KS11",
        "search_queries": [
            "https://www.google.com/search?q=kospi+index+price&hl=en",
            "https://www.google.com/search?q=kospi+composite+index+google+finance&hl=en"
        ],
        "cutoff_ist_hour": 11,
        "cutoff_ist_min": 45,
        "cutoff_label": "11:45 AM IST (15m पहले)",
        "currency": "KRW"
    },
    "Germany (DAX)": {
        "symbol_yf": "^GDAXI",
        "search_queries": [
            "https://www.google.com/search?q=dax+40+index+price&hl=en",
            "https://www.google.com/search?q=dax+index+google+finance&hl=en"
        ],
        "cutoff_ist_hour": 21,
        "cutoff_ist_min": 15,
        "cutoff_label": "09:15 PM IST (15m पहले)",
        "currency": "EUR"
    }
}

def extract_dec(price: float) -> int:
    return int(f"{price:.2f}".split(".")[1])

def get_band(center_dec: int, half_size: int = 7) -> set:
    return {(center_dec + k) % 100 for k in range(-half_size, half_size + 1)}

def fetch_live_google_unblocked(urls: list):
    """
    Scrapes Google's real-time financial ticker directly without AWS blocking.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=3.5)
            if r.status_code == 200:
                html = r.text
                # Regex 1: Google Finance embed inside search
                m = re.search(r'data-value="([0-9.,]+)"', html)
                if not m:
                    # Regex 2: Primary Google Finance header
                    m = re.search(r'class="YMlKec fxKbKc">([0-9.,]+)<', html)
                if not m:
                    # Regex 3: Knowledge graph stock rate
                    m = re.search(r'class="[a-zA-Z0-9_\s]*IsqQVc\s*NprOfl"[^>]*>([0-9.,]+)<', html)
                
                if m:
                    val = float(m.group(1).replace(",", ""))
                    if val > 100:
                        return val
        except Exception:
            continue
    return None

@st.cache_data(ttl=10, show_spinner=False)
def load_index_realtime(meta: dict):
    cut_h = meta["cutoff_ist_hour"]
    cut_m = meta["cutoff_ist_min"]
    is_locked = (now_ist.hour > cut_h) or (now_ist.hour == cut_h and now_ist.minute >= cut_m)

    # 1. PRIMARY: Real-time Google Live Tick (Zero Delay)
    live_p = fetch_live_google_unblocked(meta["search_queries"])

    target_price = None
    target_vwap = None
    source = "GOOGLE_LIVE (Zero-Delay)"

    if live_p and live_p > 0:
        target_price = live_p
        target_vwap = live_p
        source = "GOOGLE_LIVE_REALTIME"

    # 2. FALLBACK: Yahoo Finance only if Google is unavailable
    if target_price is None:
        try:
            t = yf.Ticker(meta["symbol_yf"])
            df = t.history(period="1d", interval="1m")
            if not df.empty:
                target_price = float(df.iloc[-1]["Close"])
                target_vwap = float(df["Close"].mean())
                source = "YFINANCE_BACKUP"
            else:
                df_daily = t.history(period="5d")
                if not df_daily.empty:
                    last_row = df_daily.iloc[-1]
                    target_price = float(last_row["Close"])
                    target_vwap = float((last_row["High"] + last_row["Low"] + last_row["Close"]) / 3.0)
                    source = "YFINANCE_SETTLED_CLOSE"
        except Exception:
            pass

    if target_price is None:
        return None, is_locked

    dec_p = extract_dec(target_price)
    dec_v = extract_dec(target_vwap)
    band_p = get_band(dec_p, 7)
    band_v = get_band(dec_v, 7)

    return {
        "price": target_price,
        "dec_p": dec_p,
        "vwap": target_vwap,
        "dec_v": dec_v,
        "combined": sorted(list(band_p.union(band_v))),
        "prime": sorted(list(band_p.intersection(band_v))),
        "source": source
    }, is_locked

st.title("⚡ ग्लोबल इंडेक्स 15-मिनट प्री-क्लोज दशमलव इंजन")
st.caption("गूगल रियल-टाइम लाइव फ़ीड (शून्य विलंब) — ताइवान, दक्षिण कोरिया, जर्मनी")

if st.sidebar.button("🔄 तुरंत रिफ्रेश करें"):
    st.cache_data.clear()
    st.rerun()

cols = st.columns(3)

for idx_i, (name, meta) in enumerate(INDICES.items()):
    with cols[idx_i]:
        st.subheader(name)
        st.caption(f"🔒 कट-ऑफ: **{meta['cutoff_label']}**")

        res, locked = load_index_realtime(meta)

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
        st.write(f"• VWAP/इंडिकेटिव: **.{res['dec_v']:02d}** ({res['vwap']:,.2f})")
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
