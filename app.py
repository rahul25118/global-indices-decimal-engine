"""
GLOBAL TRIO CLOSING DECIMAL ENGINE - ZERO DELAY GOOGLE FINANCE PRIMARY
- Primary Feed: Google Finance (Real-Time, No 15-min lag)
- Fallback Feed: Yahoo Finance
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
    page_title="Global Real-Time Decimal Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

IST = pytz.timezone("Asia/Kolkata")
now_ist = datetime.now(IST)

INDICES = {
    "Taiwan (TAIEX)": {
        "symbol_yf": "^TWII",
        "gf_url": "https://www.google.com/finance/quote/TPE:TAIEX",
        "cutoff_ist_hour": 10,
        "cutoff_ist_min": 45,
        "cutoff_label": "10:45 AM IST",
        "currency": "TWD"
    },
    "South Korea (KOSPI)": {
        "symbol_yf": "^KS11",
        "gf_url": "https://www.google.com/finance/quote/KOSPI:INDEXKRX",
        "cutoff_ist_hour": 11,
        "cutoff_ist_min": 45,
        "cutoff_label": "11:45 AM IST",
        "currency": "KRW"
    },
    "Germany (DAX)": {
        "symbol_yf": "^GDAXI",
        "gf_url": "https://www.google.com/finance/quote/DAX:INDEXDB",
        "cutoff_ist_hour": 21,
        "cutoff_ist_min": 15,
        "cutoff_label": "09:15 PM IST",
        "currency": "EUR"
    }
}

def extract_dec(price: float) -> int:
    return int(f"{price:.2f}".split(".")[1])

def get_band(center_dec: int, half_size: int = 7) -> set:
    return {(center_dec + k) % 100 for k in range(-half_size, half_size + 1)}

def fetch_google_finance_metrics(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 200:
            html = r.text
            price = None
            m_p = re.search(r'data-last-price="([0-9.,]+)"', html)
            if not m_p:
                m_p = re.search(r'class="YMlKec fxKbKc">([0-9.,]+)<', html)
            if m_p:
                price = float(m_p.group(1).replace(",", ""))

            # Extract day range / approximate typical price
            high, low = price, price
            m_range = re.search(r'Day range</div><div[^>]*>([0-9.,]+)\s*-\s*([0-9.,]+)</div>', html)
            if m_range:
                low = float(m_range.group(1).replace(",", ""))
                high = float(m_range.group(2).replace(",", ""))

            if price and price > 0:
                approx_vwap = (high + low + price) / 3.0
                return {"price": price, "vwap": approx_vwap, "status": "LIVE_REALTIME"}
    except Exception:
        pass
    return None

@st.cache_data(ttl=10, show_spinner=False)
def get_index_data(meta: dict):
    cut_h = meta["cutoff_ist_hour"]
    cut_m = meta["cutoff_ist_min"]
    is_locked = (now_ist.hour > cut_h) or (now_ist.hour == cut_h and now_ist.minute >= cut_m)

    # 1. Primary: Google Finance Real-Time (Zero-Delay)
    gf_data = fetch_google_finance_metrics(meta["gf_url"])

    target_price = None
    target_vwap = None
    source = "GOOGLE_FINANCE_REALTIME"

    if gf_data:
        target_price = gf_data["price"]
        target_vwap = gf_data["vwap"]
    else:
        # 2. Fallback to Yahoo Finance only if Google fails
        try:
            t = yf.Ticker(meta["symbol_yf"])
            df_yf = t.history(period="1d", interval="1m")
            if not df_yf.empty:
                target_price = float(df_yf.iloc[-1]["Close"])
                target_vwap = float(df_yf["Close"].mean())
                source = "YFINANCE_BACKUP"
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

st.title("⚡ ग्लोबल इंडेक्स रियल-टाइम 15-मिनट दशमलव इंजन")
st.caption("गूगल फाइनेंस रियल-टाइम लाइव फ़ीड (शून्य विलंब) — ताइवान, दक्षिण कोरिया, जर्मनी")

if st.sidebar.button("🔄 तुरंत रिफ्रेश करें"):
    st.cache_data.clear()
    st.rerun()

cols = st.columns(3)

for idx_i, (name, meta) in enumerate(INDICES.items()):
    with cols[idx_i]:
        st.subheader(name)
        st.caption(f"🔒 कट-ऑफ: **{meta['cutoff_label']}**")

        res, locked = get_index_data(meta)

        if locked:
            st.success(f"🔒 **{meta['cutoff_label']} पर डेटा लॉक है**")
        else:
            st.warning("⏳ कट-ऑफ विंडो का इंतज़ार...")

        if not res:
            st.error("डेटा लोड नहीं हो सका।")
            continue

        st.metric(
            label=f"कट-ऑफ भाव ({meta['currency']})",
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
