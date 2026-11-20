import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import time

# १. पेज सेटअप - स्वच्छ आणि सुटसुटीत लेआउट
st.set_page_config(page_title="Pro Option Paper Algo", layout="wide")

if not os.path.exists("reports"):
    os.makedirs("reports")

# सेशन स्टेट्स इनिशियलायझेशन
if "capital" not in st.session_state:
    st.session_state.capital = 100000.0
if "trades" not in st.session_state:
    st.session_state.trades = []
if "active_trade" not in st.session_state:
    st.session_state.active_trade = None
if "lot_settings" not in st.session_state:
    st.session_state.lot_settings = {"NIFTY": 2, "BANKNIFTY": 1, "SENSEX": 1}
if "risk_settings" not in st.session_state:
    st.session_state.risk_settings = {
        "sl_pct": 15.0,
        "target_pct": 30.0,
        "trailing_sl": True,
        "max_daily_loss": 5000.0,
        "max_trades": 3
    }

# इंडेक्सनुसार लॉट साईज (Qty per Lot)
LOT_MULTIPLIER = {"NIFTY": 75, "BANKNIFTY": 30, "SENSEX": 20}

# --- अल्गो ट्रेडिंग इंजिन (Price Action + Option Chain Rules) ---
def check_algo_signal(spot, ema, pcr, strategy):
    """
    प्राईज ॲक्शन आणि ऑप्शन चेन (PCR) तपासून BUY CE किंवा BUY PE सिग्नल देते.
    """
    if strategy == "15-Min ORB + OI Confirmation":
        if spot > ema * 1.001 and pcr > 1.05:
            return "CE", "Breakout Above Resistance + Strong Put Writing (Bullish)"
        elif spot < ema * 0.999 and pcr < 0.95:
            return "PE", "Breakdown Below Support + Strong Call Writing (Bearish)"
            
    elif strategy == "EMA Pullback + Price Action":
        if abs(spot - ema) / ema < 0.0008 and pcr >= 1.0:
            return "CE", "Bullish Pullback at 20 EMA + Positive OI"
        elif abs(spot - ema) / ema < 0.0008 and pcr < 1.0:
            return "PE", "Bearish Rejection at 20 EMA + Negative OI"
            
    return None, "Waiting for Setup..."

# --- डावा साईडबार (कंट्रोल पॅनेल) ---
with st.sidebar:
    st.title("⚡ Option Paper Algo")
    st.caption("Status: **PAPER MODE (Zero Risk)**")
    st.divider()
    
    index_choice = st.selectbox("इंडेक्स निवडा (Index)", ["NIFTY", "BANKNIFTY", "SENSEX"])
    strategy_choice = st.selectbox(
        "प्राईज ॲक्शन स्ट्रॅटेजी", 
        ["15-Min ORB + OI Confirmation", "EMA Pullback + Price Action"]
    )
    
    st.divider()
    algo_running = st.toggle("🟢 अल्गो चालू करा (Auto Trade)", value=False)
    
    if st.button("🔄 Reset Day / Clear Trades", use_container_width=True):
        st.session_state.trades = []
        st.session_state.active_trade = None
        st.rerun()

# --- सिम्युलेटेड मार्केट डेटा (पुढे येथे Zerodha API जोडला जाईल) ---
base_price = 24350.0 if index_choice == "NIFTY" else (52180.0 if index_choice == "BANKNIFTY" else 80120.0)
step = 50 if index_choice == "NIFTY" else 100

# मार्केट हालचाल तयार करणे
spot_price = round(base_price + np.random.uniform(-65, 65), 2)
ema_20 = round(base_price + np.random.uniform(-20, 20), 2)
atm_strike = int(round(spot_price / step) * step)
pcr_ratio = round(np.random.uniform(0.75, 1.35), 2)

# आजचा एकूण P&L मोजणे
closed_pnl = sum([t["P&L"] for t in st.session_state.trades])
open_pnl = 0.0

# --- जर एखादा ट्रेड चालू असेल तर SL / Target तपासणे ---
if st.session_state.active_trade:
    trade = st.session_state.active_trade
    # ऑप्शन प्रीमियमची हालचाल
    price_change = np.random.uniform(-12, 18)
    current_ltp = round(max(5.0, trade["Entry"] + price_change), 2)
    trade["Current_LTP"] = current_ltp
    open_pnl = round((current_ltp - trade["Entry"]) * trade["Qty"], 2)
    
    # Trailing SL लॉजिक (जर प्रीमियम 15% वाढला तर SL खरेदी किमतीवर आणा)
    if st.session_state.risk_settings["trailing_sl"] and current_ltp >= trade["Entry"] * 1.15:
        if trade["SL"] < trade["Entry"]:
            trade["SL"] = trade["Entry"]
            
    # Exit अटी तपासणे (Stop Loss किंवा Target)
    exit_reason = None
    if current_ltp <= trade["SL"]:
        exit_reason = "Stop-Loss Hit"
    elif current_ltp >= trade["Target"]:
        exit_reason = "Target Achieved"
        
    if exit_reason:
        st.session_state.trades.append({
            "Time": datetime.now().strftime("%H:%M:%S"),
            "Symbol": trade["Symbol"],
            "Qty": trade["Qty"],
            "Entry": trade["Entry"],
            "Exit": current_ltp,
            "P&L": open_pnl,
            "Reason": exit_reason
        })
        st.session_state.active_trade = None
        open_pnl = 0.0

# --- जर अल्गो चालू असेल आणि कोणताही ट्रेड ओपन नसेल तर नवीन एंट्री तपासणे ---
signal_msg = "Algo Paused"
if algo_running:
    total_today_pnl = closed_pnl + open_pnl
    if total_today_pnl <= -st.session_state.risk_settings["max_daily_loss"]:
        signal_msg = "🛑 Max Daily Loss Reached! Algo Stopped."
    elif len(st.session_state.trades) >= st.session_state.risk_settings["max_trades"]:
        signal_msg = "🛑 Max Daily Trades Limit Reached."
    elif st.session_state.active_trade is None:
        opt_type, reason = check_algo_signal(spot_price, ema_20, pcr_ratio, strategy_choice)
        signal_msg = reason
        if opt_type:
            qty = st.session_state.lot_settings[index_choice] * LOT_MULTIPLIER[index_choice]
            entry_ltp = round(np.random.uniform(120, 180), 2)
            sl_price = round(entry_ltp * (1 - st.session_state.risk_settings["sl_pct"] / 100), 2)
            tgt_price = round(entry_ltp * (1 + st.session_state.risk_settings["target_pct"] / 100), 2)
            
            st.session_state.active_trade = {
                "Symbol": f"{index_choice} {atm_strike} {opt_type}",
                "Qty": qty,
                "Entry": entry_ltp,
                "Current_LTP": entry_ltp,
                "SL": sl_price,
                "Target": tgt_price,
                "Reason": reason
            }

# --- वरचा स्टेटस बार (सुटसुटीत ४ आकडे) ---
total_pnl = round(closed_pnl + open_pnl, 2)
col1, col2, col3, col4 = st.columns(4)
col1.metric(f"{index_choice} Spot", f"₹{spot_price:,.2f}", f"ATM: {atm_strike}")
col2.metric("Paper Capital", f"₹{st.session_state.capital + total_pnl:,.2f}")
col3.metric("Today's Net P&L", f"₹{total_pnl:,.2f}", delta=f"{total_pnl:,.2f}")
col4.metric("Active Lots", f"{st.session_state.lot_settings[index_choice]} Lots ({st.session_state.lot_settings[index_choice] * LOT_MULTIPLIER[index_choice]} Qty)")

st.divider()

# --- ४ स्वच्छ टॅब्स ---
tab1, tab2, tab3, tab4 = st.tabs([
    "🎯 Live Algo & Trades", 
    "⛓️ Option Chain (OI)", 
    "📦 Lot Size & Risk", 
    "📑 Backtest & Reports"
])

# टॅब १: लाईव्ह अल्गो पोझिशन आणि ट्रेड लॉग
with tab1:
    st.info(f"**Algo Scanner Status:** {signal_msg}")
    
    # चालू असलेली पोझिशन (Open Position)
    if st.session_state.active_trade:
        t = st.session_state.active_trade
        st.markdown("#### 🟢 चालू असलेला ट्रेड (Active Position)")
        p1, p2, p3, p4, p5 = st.columns(5)
        p1.metric("Contract", t["Symbol"])
        p2.metric("Buy Price", f"₹{t['Entry']}")
        p3.metric("Live LTP", f"₹{t['Current_LTP']}", f"₹{open_pnl}")
        p4.metric("Stop-Loss", f"₹{t['SL']}")
        p5.metric("Target", f"₹{t['Target']}")
        
        if st.button("❌ Exit Position Now (Manual Square-off)"):
            st.session_state.trades.append({
                "Time": datetime.now().strftime("%H:%M:%S"),
                "Symbol": t["Symbol"],
                "Qty": t["Qty"],
                "Entry": t["Entry"],
                "Exit": t["Current_LTP"],
                "P&L": open_pnl,
                "Reason": "Manual Exit"
            })
            st.session_state.active_trade = None
            st.rerun()
    
    st.markdown("#### 📜 पूर्ण झालेले पेपर ट्रेड्स (Completed Trades)")
    if st.session_state.trades:
        st.dataframe(pd.DataFrame(st.session_state.trades), use_container_width=True, hide_index=True)
    else:
        st.caption("अद्याप कोणताही ट्रेड पूर्ण झालेला नाही. अल्गो चालू केल्यावर सिग्नल मिळताच येथे ट्रेड दिसेल.")

# टॅब २: ऑप्शन चेन आणि OI विश्लेषण
with tab2:
    c_oc1, c_oc2 = st.columns([3, 1])
    c_oc1.markdown(f"#### {index_choice} Option Chain (PCR: {pcr_ratio})")
    sentiment = "Bullish (खरेदीचा कल)" if pcr_ratio > 1.05 else ("Bearish (विक्रीचा कल)" if pcr_ratio < 0.95 else "Sideways")
    c_oc2.metric("OI Sentiment", sentiment)
    
    strikes = [atm_strike - 2*step, atm_strike - step, atm_strike, atm_strike + step, atm_strike + 2*step]
    oc_rows = []
    for s in strikes:
        oc_rows.append({
            "CALL OI (Lakhs)": round(np.random.uniform(15, 90), 2),
            "CALL LTP (₹)": round(max(12, (spot_price - s) + 125), 2),
            "STRIKE": f"{s} {'(ATM)' if s == atm_strike else ''}",
            "PUT LTP (₹)": round(max(12, (s - spot_price) + 120), 2),
            "PUT OI (Lakhs)": round(np.random.uniform(15, 90), 2),
        })
    st.dataframe(pd.DataFrame(oc_rows), use_container_width=True, hide_index=True)

# टॅब ३: Lot Size आणि Risk Management साठी स्वतंत्र टॅब
with tab3:
    st.markdown("#### 📦 Lot Size आणि रिस्क मॅनेजमेंट सेटिंग्ज")
    col_l, col_r = st.columns(2)
    
    with col_l:
        st.subheader("१. Lot Size निवडा")
        n_lots = st.number_input("NIFTY Lots (1 Lot = 75)", 1, 50, st.session_state.lot_settings["NIFTY"])
        b_lots = st.number_input("BANKNIFTY Lots (1 Lot = 30)", 1, 50, st.session_state.lot_settings["BANKNIFTY"])
        s_lots = st.number_input("SENSEX Lots (1 Lot = 20)", 1, 50, st.session_state.lot_settings["SENSEX"])
        
    with col_r:
        st.subheader("२. Stop-Loss आणि Target नियम")
        sl_val = st.slider("Stop-Loss (% प्रीमियमवर)", 5.0, 50.0, st.session_state.risk_settings["sl_pct"])
        tgt_val = st.slider("Target (% प्रीमियमवर)", 10.0, 150.0, st.session_state.risk_settings["target_pct"])
        tsl_val = st.checkbox("Trailing SL चालू ठेवा (15% नफ्यावर SL Cost वर आणा)", value=st.session_state.risk_settings["trailing_sl"])
