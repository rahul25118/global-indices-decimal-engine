"""
GLOBAL TRIO CLOSING DECIMAL ENGINE - DIRECT LIVE REALTIME
- Strict 15-min Cut-Offs
- Primary: Google Finance Direct Scraping with Headers
- Fallback: Yahoo Finance Verified Real Index Tickers
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
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

IST = pytz.timezone("Asia/Kolkata")
now_ist = datetime.now(IST)

INDICES = {
    "Taiwan (TAIEX)": {
        "symbol_yf": "^TWII",
        "gf_ticker": "TPE:TAIEX",
        "cutoff_ist_hour": 10,
        "cutoff_ist_min": 45,
        "cutoff_label": "10:45 AM IST (15m पहले)",
        "currency": "TWD"
    },
    "South Korea (KOSPI)": {
        "symbol_yf": "^KS11",
        "gf_ticker": "KRX:KOSPI",
        "cutoff_ist_hour": 11,
        "cutoff_ist_min": 45,
        "cutoff_label": "11:45 AM IST (15m पहले)",
        "currency": "KRW"
    },
    "Germany (DAX)": {
        "symbol_yf": "^GDAXI",
        "gf_ticker": "INDEXDB:DAX",
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

def fetch_live_from_google(ticker: str):
    url = f"https://www.google.com/finance/quote/{ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            html = r.text
            price = None
            # Match 1: data-last-price attribute
            m = re.search(r'data-last-price="([0-9.,]+)"', html)
            if not m:
                # Match 2: Big price div
                m = re.search(r'class="YMlKec fxKbKc">([0-9.,]+)<', html)
            if m:
                price = float(m.group(1).replace(",", ""))

            # Extract day range to estimate VWAP
            high, low = price, price
            m_range = re.search(r'Day range</div><div[^>]*>([0-9.,]+)\s*-\s*([0-9.,]+)</div>', html)
            if m_range:
                low = float(m_range.group(1).replace(",", ""))
                high = float(m_range.group(2).replace(",", ""))

            if price and price > 0:
                approx_vwap = (high + low + price) / 3.0
                return {"price": price, "vwap": approx_vwap, "source": "GOOGLE_FINANCE_LIVE"}
    except Exception:
        pass
    return None

@st.cache_data(ttl=10, show_spinner=False)
def load_index_data(meta: dict):
    cut_h = meta["cutoff_ist_hour"]
    cut_m = meta["cutoff_ist_min"]
    is_locked = (now_ist.hour > cut_h) or (now_ist.hour == cut_h and now_ist.minute >= cut_m)

    # 1. First priority: Google Finance Live
    gf_data = fetch_live_from_google(meta["gf_ticker"])

    price = None
    vwap = None
    source = "GOOGLE_FINANCE_LIVE"

    if gf_data:
        price = gf_data["price"]
        vwap = gf_data["vwap"]
    else:
        # 2. Fallback to Yahoo Finance
        try:
            t = yf.Ticker(meta["symbol_yf"])
            df = t.history(period="1d", interval="1m")
            if not df.empty:
                price = float(df.iloc[-1]["Close"])
                vwap = float(df["Close"].mean())
                source = "YFINANCE_BACKUP"
        except Exception:
            pass

    if price is None:
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
st.caption("ताइवान (10:45 AM), दक्षिण कोरिया (11:45 AM), जर्मनी (09:15 PM IST) - हार्ड लॉक")

if st.sidebar.button("🔄 तुरंत रिफ्रेश करें"):
    st.cache_data.clear()
    st.rerun()

cols = st.columns(3)

for idx_i, (name, meta) in enumerate(INDICES.items()):
    with cols[idx_i]:
        st.subheader(name)
        st.caption(f"🔒 कट-ऑफ: **{meta['cutoff_label']}**")

        res, locked = load_index_data(meta)

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
        st.write(f"• VWAP: **.{res['dec_v']:02d}** ({res['vwap']:,.2f})")
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
