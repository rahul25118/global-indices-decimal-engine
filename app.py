"""
GLOBAL TRIO CLOSING DECIMAL ENGINE - 15-MIN PRE-CLOSE (FIXED FEEDS)
Strictly freezes numbers 15 minutes before respective market closing.
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
    page_title="Global 15-Min Decimal Engine",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded"
)

IST = pytz.timezone("Asia/Kolkata")
now_ist = datetime.now(IST)

INDICES = {
    "Taiwan (TAIEX)": {
        "symbol_yf": "^TWII",
        "gf_urls": [
            "https://www.google.com/finance/quote/TPE:TAIEX",
            "https://www.google.com/finance/quote/.TWII:INDEX"
        ],
        "close_ist": "11:00 AM",
        "cutoff_ist_hour": 10,
        "cutoff_ist_min": 45,
        "cutoff_label": "10:45 AM IST (15m पहले)",
        "currency": "TWD"
    },
    "South Korea (KOSPI)": {
        "symbol_yf": "^KS11",
        "gf_urls": [
            "https://www.google.com/finance/quote/KOSPI:INDEXKRX",
            "https://www.google.com/finance/quote/KRX:KOSPI"
        ],
        "close_ist": "12:00 PM",
        "cutoff_ist_hour": 11,
        "cutoff_ist_min": 45,
        "cutoff_label": "11:45 AM IST (15m पहले)",
        "currency": "KRW"
    },
    "Germany (DAX)": {
        "symbol_yf": "^GDAXI",
        "gf_urls": [
            "https://www.google.com/finance/quote/DAX:INDEXDB"
        ],
        "close_ist": "10:00 PM",
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

def fetch_live_price_google(urls: list):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    for u in urls:
        try:
            r = requests.get(u, headers=headers, timeout=4)
            if r.status_code == 200:
                m = re.search(r'data-last-price="([0-9.,]+)"', r.text)
                if not m:
                    m = re.search(r'class="YMlKec fxKbKc">([0-9.,]+)<', r.text)
                if m:
                    val = float(m.group(1).replace(",", ""))
                    if val > 0:
                        return val
        except Exception:
            pass
    return None

@st.cache_data(ttl=20, show_spinner=False)
def load_data_and_compute(meta: dict):
    # 1. Fetch Google Finance live / settlement price
    gf_price = fetch_live_price_google(meta["gf_urls"])

    # 2. Fetch Historical Bars via Yahoo Finance with multi-interval fallback
    df_yf = pd.DataFrame()
    t = yf.Ticker(meta["symbol_yf"])
    for interval in ["1m", "2m", "5m"]:
        try:
            df_cand = t.history(period="5d", interval=interval)
            if not df_cand.empty and len(df_cand) >= 5:
                df_yf = df_cand
                break
        except Exception:
            pass

    target_price = None
    target_vwap = None
    source_used = "YFINANCE"

    if not df_yf.empty:
        if df_yf.index.tz is None:
            df_yf.index = df_yf.index.tz_localize("UTC").tz_convert(IST)
        else:
            df_yf.index = df_yf.index.tz_convert(IST)

        last_date = df_yf.index[-1].date()
        df_today = df_yf[df_yf.index.date == last_date].copy()

        cut_h = meta["cutoff_ist_hour"]
        cut_m = meta["cutoff_ist_min"]

        # Filter bars at or before the 15-minute pre-close cutoff
        mask = (df_today.index.hour < cut_h) | ((df_today.index.hour == cut_h) & (df_today.index.minute <= cut_m))
        df_cut = df_today[mask]

        if not df_cut.empty:
            target_price = float(df_cut.iloc[-1]["Close"])
            win = df_cut.tail(15)
            typ_p = (win["High"] + win["Low"] + win["Close"]) / 3.0
            vol = win["Volume"]
            target_vwap = (typ_p * vol).sum() / vol.sum() if vol.sum() > 0 else typ_p.mean()
            source_used = f"YFINANCE_HISTORICAL ({interval} bars)"
        else:
            # If session is already over and bars started after cutoff, use earliest bar of closing session
            target_price = float(df_today.iloc[0]["Close"])
            target_vwap = target_price
            source_used = "YFINANCE_SESSION_SETTLE"

    # Fallback to Google Finance price if YF failed completely
    if target_price is None or target_price <= 0:
        if gf_price and gf_price > 0:
            target_price = gf_price
            target_vwap = gf_price
            source_used = "GOOGLE_FINANCE_LIVE"

    if target_price is None or target_price <= 0:
        return None

    dec_p = extract_dec(target_price)
    dec_v = extract_dec(target_vwap)

    band_p = get_band(dec_p, 7)
    band_v = get_band(dec_v, 7)

    return {
        "price": target_price,
        "dec_price": dec_p,
        "vwap": target_vwap,
        "dec_vwap": dec_v,
        "combined": sorted(list(band_p.union(band_v))),
        "prime": sorted(list(band_p.intersection(band_v))),
        "source": source_used
    }

st.title("🌐 ग्लोबल इंडेक्स 15-मिनट प्री-क्लोज दशमलव इंजन")
st.caption("क्लोजिंग से ठीक 15 मिनट पहले का डेटा फ़्रीज़ / लॉक (ताइवान, दक्षिण कोरिया, जर्मनी)")

st.sidebar.header("⚙️ सेटिंग्स")
if st.sidebar.button("🔄 तुरंत रिफ्रेश करें"):
    st.cache_data.clear()
    st.rerun()

cols = st.columns(3)

for idx_i, (name, meta) in enumerate(INDICES.items()):
    with cols[idx_i]:
        st.subheader(name)
        st.caption(f"🔒 कट-ऑफ: **{meta['cutoff_label']}** (क्लोज: {meta['close_ist']})")

        is_locked = (now_ist.hour > meta["cutoff_ist_hour"]) or (
            now_ist.hour == meta["cutoff_ist_hour"] and now_ist.minute >= meta["cutoff_ist_min"]
        )

        if is_locked:
            st.success("🔒 **15 मिनट पहले का डेटा लॉक है**")
        else:
            st.warning("⏳ 15 मिनट कट-ऑफ विंडो का इंतज़ार...")

        res = load_data_and_compute(meta)

        if not res:
            st.error("डेटा लोड नहीं हो सका।")
            continue

        st.metric(
            label=f"15m कट-ऑफ भाव ({meta['currency']})",
            value=f"{res['price']:,.2f}",
            delta=f"दशमलव: .{res['dec_price']:02d}"
        )
        st.write(f"• 15m VWAP: **.{res['dec_vwap']:02d}** ({res['vwap']:,.2f})")
        st.write(f"• डेटा स्रोत: `{res['source']}`")

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
