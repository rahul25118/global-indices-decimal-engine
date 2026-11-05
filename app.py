"""
GLOBAL TRIO CLOSING DECIMAL ENGINE - 15-MIN PRE-CLOSE CUTOFF
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
        "gf_symbol": "TPE:TAIEX",
        "tz_name": "Asia/Taipei",
        "close_ist": "11:00 AM",
        "cutoff_ist_hour": 10,
        "cutoff_ist_min": 45,
        "cutoff_label": "10:45 AM IST (15m पहले)",
        "currency": "TWD",
        "approx_range": (20000, 26000)
    },
    "South Korea (KOSPI)": {
        "symbol_yf": "^KS11",
        "gf_symbol": "KRX:KOSPI",
        "tz_name": "Asia/Seoul",
        "close_ist": "12:00 PM",
        "cutoff_ist_hour": 11,
        "cutoff_ist_min": 45,
        "cutoff_label": "11:45 AM IST (15m पहले)",
        "currency": "KRW",
        "approx_range": (2300, 2900)
    },
    "Germany (DAX)": {
        "symbol_yf": "^GDAXI",
        "gf_symbol": "INDEXDB:DAX",
        "tz_name": "Europe/Berlin",
        "close_ist": "10:00 PM",
        "cutoff_ist_hour": 21,
        "cutoff_ist_min": 45,
        "cutoff_label": "09:45 PM IST (15m पहले)",
        "currency": "EUR",
        "approx_range": (18000, 26000)
    }
}

def extract_dec(price: float) -> int:
    return int(f"{price:.2f}".split(".")[1])

def get_band(center_dec: int, half_size: int = 7) -> set:
    return {(center_dec + k) % 100 for k in range(-half_size, half_size + 1)}

def fetch_live_price_google(gf_sym: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    url = f"https://www.google.com/finance/quote/{gf_sym}"
    try:
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 200:
            m = re.search(r'data-last-price="([0-9.,]+)"', r.text)
            if not m:
                m = re.search(r'class="YMlKec fxKbKc">([0-9.,]+)<', r.text)
            if m:
                return float(m.group(1).replace(",", ""))
    except Exception:
        pass
    return None

@st.cache_data(ttl=15, show_spinner=False)
def load_data_and_compute(meta: dict):
    # 1. Check Live Google Finance Price
    gf_price = fetch_live_price_google(meta["gf_symbol"])

    # 2. Fetch Historical Bars via Yahoo
    df_yf = pd.DataFrame()
    try:
        t = yf.Ticker(meta["symbol_yf"])
        df_yf = t.history(period="5d", interval="1m")
    except Exception:
        pass

    target_price = None
    target_vwap = None
    source_used = "GOOGLE_FINANCE_LIVE"

    if not df_yf.empty:
        # Convert index to IST for strict 15-min pre-close matching
        if df_yf.index.tz is None:
            df_yf.index = df_yf.index.tz_localize("UTC").tz_convert(IST)
        else:
            df_yf.index = df_yf.index.tz_convert(IST)

        last_date = df_yf.index[-1].date()
        df_today = df_yf[df_yf.index.date == last_date].copy()

        # Apply Strict Cutoff: Only rows <= 15-min cutoff time
        cut_h = meta["cutoff_ist_hour"]
        cut_m = meta["cutoff_ist_min"]

        # Filter rows at or before cutoff
        mask = (df_today.index.hour < cut_h) | ((df_today.index.hour == cut_h) & (df_today.index.minute <= cut_m))
        df_cut = df_today[mask]

        if not df_cut.empty:
            p_cand = float(df_cut.iloc[-1]["Close"])
            # Validate price sanity
            low_b, high_b = meta["approx_range"]
            if low_b <= p_cand <= high_b:
                target_price = p_cand
                win = df_cut.tail(20)
                typ_p = (win["High"] + win["Low"] + win["Close"]) / 3.0
                vol = win["Volume"]
                target_vwap = (typ_p * vol).sum() / vol.sum() if vol.sum() > 0 else typ_p.mean()
                source_used = "YFINANCE_HISTORICAL_CUTOFF"

    # Fallback to Google Finance if YF was out of range or empty
    if target_price is None:
        if gf_price and meta["approx_range"][0] <= gf_price <= meta["approx_range"][1]:
            target_price = gf_price
            target_vwap = gf_price
            source_used = "GOOGLE_FINANCE_LIVE"

    if target_price is None:
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

        # Check if currently locked
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
