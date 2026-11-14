import io
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

PIP = 0.0001  # AUD USD mein 1 pip = 0.0001
S = st.session_state

st.set_page_config(page_title="AUD USD Manual Backtest", layout="wide")
st.title("AUD USD Manual Backtest")

# ---------------- Sidebar ----------------
st.sidebar.header("Settings")
file = st.sidebar.file_uploader("CSV upload karo (audusd.csv)", type=["csv"])
st.sidebar.number_input("Stop loss (pips)", min_value=0.0, value=10.0, step=1.0, key="sl_pips")
st.sidebar.number_input("Target (pips, 0 = koi target nahi)", min_value=0.0, value=20.0, step=1.0, key="tp_pips")
st.sidebar.number_input("Chart mein kitni candles", min_value=50, max_value=500, value=150, step=10, key="n_bars")
st.sidebar.checkbox("RSI dikhao", value=True, key="show_rsi")
st.sidebar.checkbox("EMA 5 dikhao", value=True, key="show_ema")

raw = None
if file is not None:
    raw = file.getvalue()
elif os.path.exists("audusd.csv"):
    with open("audusd.csv", "rb") as f:
        raw = f.read()

if raw is None:
    st.info("Left side (>> wale menu) se audusd.csv upload karo.")
    st.stop()


@st.cache_data
def load_data(raw_bytes):
    d = pd.read_csv(io.BytesIO(raw_bytes))
    d.columns = [str(c).lower().strip() for c in d.columns]
    if "time" not in d.columns:
        d = d.rename(columns={d.columns[0]: "time"})
    d["time"] = pd.to_datetime(d["time"])
    d = d.sort_values("time").reset_index(drop=True)
    d = d[["time", "open", "high", "low", "close"]].copy()
    delta = d["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    d["rsi"] = 100 - (100 / (1 + rs))
    d["ema5"] = d["close"].ewm(span=5, adjust=False).mean()
    d["ts"] = d["time"].dt.strftime("%Y-%m-%d %H:%M")
    return d


df = load_data(raw)
if len(df) < 60:
    st.error("CSV mein bohot kam candles hain. Kam se kam 60 candles chahiye.")
    st.stop()

HI = df["high"].values
LO = df["low"].values
CL = df["close"].values
TS = df["ts"].values

# ---------------- State ----------------
sig = (len(df), str(df["time"].iloc[0]), str(df["time"].iloc[-1]))
if S.get("sig") != sig:
    S.sig = sig
    S.i = min(300, len(df) - 2)
    S.pos = None
    S.trades = []

if "start_date" not in S:
    S.start_date = df["time"].iloc[S.i].date()

st.sidebar.date_input("Replay is date se shuru karo", key="start_date")


def do_reset():
    d0 = pd.Timestamp(S.start_date)
    idx = df.index[df["time"] >= d0]
    i = int(idx[0]) if len(idx) else len(df) - 2
    S.i = max(50, min(i, len(df) - 2))
    S.pos = None
    S.trades = []


st.sidebar.button("Shuru / Reset", on_click=do_reset, key="btn_reset")


def close_pos(price, t, reason):
    p = S.pos
    if p is None:
        return
    if p["side"] == "BUY":
        pips = (price - p["entry"]) / PIP
    else:
        pips = (p["entry"] - price) / PIP
    S.trades.append(
        {
            "side": p["side"],
            "entry_time": p["time"],
            "entry": p["entry"],
            "exit_time": t,
            "exit": float(price),
            "pips": round(float(pips), 1),
            "reason": reason,
        }
    )
    S.pos = None


def check_exit(k):
    p = S.pos
    if p is None:
        return
    t = TS[k]
    if p["side"] == "BUY":
        if p["sl"] is not None and LO[k] <= p["sl"]:
            close_pos(p["sl"], t, "SL")
        elif p["tp"] is not None and HI[k] >= p["tp"]:
            close_pos(p["tp"], t, "TP")
    else:
        if p["sl"] is not None and HI[k] >= p["sl"]:
            close_pos(p["sl"], t, "SL")
        elif p["tp"] is not None and LO[k] <= p["tp"]:
            close_pos(p["tp"], t, "TP")


def step(n):
    for _ in range(n):
        if S.i >= len(df) - 1:
            break
        S.i += 1
        check_exit(S.i)


def open_trade(side):
    if S.pos is not None:
        return
    entry = float(CL[S.i])
    sl_p = float(S.sl_pips) * PIP
    tp_p = float(S.tp_pips) * PIP
    if side == "BUY":
        sl = entry - sl_p if sl_p > 0 else None
        tp = entry + tp_p if tp_p > 0 else None
    else:
        sl = entry + sl_p if sl_p > 0 else None
        tp = entry - tp_p if tp_p > 0 else None
    S.pos = {"side": side, "entry": entry, "sl": sl, "tp": tp, "time": TS[S.i]}


def manual_close():
    if S.pos is not None:
        close_pos(CL[S.i], TS[S.i], "Manual")


# ---------------- Controls ----------------
at_end = S.i >= len(df) - 1
c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
c1.button("Aage 1", on_click=step, args=(1,), key="n1", disabled=at_end)
c2.button("Aage 5", on_click=step, args=(5,), key="n5", disabled=at_end)
c3.button("Aage 10", on_click=step, args=(10,), key="n10", disabled=at_end)
c4.button("Aage 30", on_click=step, args=(30,), key="n30", disabled=at_end)
c5.button("BUY", on_click=open_trade, args=("BUY",), key="buy", disabled=S.pos is not None)
c6.button("SELL", on_click=open_trade, args=("SELL",), key="sell", disabled=S.pos is not None)
c7.button("Trade band karo", on_click=manual_close, key="close", disabled=S.pos is None)

now_t = df["time"].iloc[S.i]
h = now_t.hour
in_no_trade = h >= 20 or h < 6
status = f"Abhi ka waqt: {now_t:%Y-%m-%d %H:%M}   |   Price: {CL[S.i]:.5f}"
if S.pos is not None:
    p = S.pos
    if p["side"] == "BUY":
        live = (CL[S.i] - p["entry"]) / PIP
    else:
        live = (p["entry"] - CL[S.i]) / PIP
    status += f"   |   Open {p['side']} @ {p['entry']:.5f}, abhi {live:+.1f} pips"
st.markdown(status)
if in_no_trade:
    st.warning("Yeh waqt aapke no-trade time (raat 8 se subah 6) mein hai.")
if at_end:
    st.info("Data khatam ho gaya. Reset dabao ya naya CSV upload karo.")

# ---------------- Chart ----------------
lo_i = max(0, S.i - int(S.n_bars) + 1)
w = df.iloc[lo_i : S.i + 1]
visible = set(w["ts"])
show_rsi = bool(S.show_rsi)
rows = 2 if show_rsi else 1
fig = make_subplots(
    rows=rows,
    cols=1,
    shared_xaxes=True,
    row_heights=[0.72, 0.28] if show_rsi else [1.0],
    vertical_spacing=0.03,
)
fig.add_trace(
    go.Candlestick(
        x=w["ts"],
        open=w["open"],
        high=w["high"],
        low=w["low"],
        close=w["close"],
        name="AUDUSD",
    ),
    row=1,
    col=1,
)
if S.show_ema:
    fig.add_trace(
        go.Scatter(x=w["ts"], y=w["ema5"], mode="lines", name="EMA 5", line=dict(width=1.3, color="orange")),
        row=1,
        col=1,
    )

buy_x, buy_y, sell_x, sell_y, exit_x, exit_y = [], [], [], [], [], []
all_trades = list(S.trades)
for tr in all_trades:
    if tr["entry_time"] in visible:
        (buy_x if tr["side"] == "BUY" else sell_x).append(tr["entry_time"])
        (buy_y if tr["side"] == "BUY" else sell_y).append(tr["entry"])
    if tr["exit_time"] in visible:
        exit_x.append(tr["exit_time"])
        exit_y.append(tr["exit"])
if S.pos is not None and S.pos["time"] in visible:
    (buy_x if S.pos["side"] == "BUY" else sell_x).append(S.pos["time"])
    (buy_y if S.pos["side"] == "BUY" else sell_y).append(S.pos["entry"])

if buy_x:
    fig.add_trace(
        go.Scatter(x=buy_x, y=buy_y, mode="markers", name="BUY", marker=dict(symbol="triangle-up", size=13, color="lime")),
        row=1,
        col=1,
    )
if sell_x:
    fig.add_trace(
        go.Scatter(x=sell_x, y=sell_y, mode="markers", name="SELL", marker=dict(symbol="triangle-down", size=13, color="red")),
        row=1,
        col=1,
    )
if exit_x:
    fig.add_trace(
        go.Scatter(x=exit_x, y=exit_y, mode="markers", name="Exit", marker=dict(symbol="x", size=10, color="white")),
        row=1,
        col=1,
    )

if S.pos is not None:
    fig.add_hline(y=S.pos["entry"], line_dash="dash", line_color="white", row=1, col=1)
    if S.pos["sl"] is not None:
        fig.add_hline(y=S.pos["sl"], line_dash="dot", line_color="red", row=1, col=1)
    if S.pos["tp"] is not None:
        fig.add_hline(y=S.pos["tp"], line_dash="dot", line_color="lime", row=1, col=1)

if show_rsi:
    fig.add_trace(
        go.Scatter(x=w["ts"], y=w["rsi"], mode="lines", name="RSI 14", line=dict(width=1.3, color="violet")),
        row=2,
        col=1,
    )
    fig.add_hline(y=70, line_dash="dot", line_color="gray", row=2, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="gray", row=2, col=1)

fig.update_xaxes(type="category", nticks=8, rangeslider_visible=False)
fig.update_layout(
    height=720,
    template="plotly_dark",
    margin=dict(l=10, r=10, t=30, b=10),
    legend=dict(orientation="h", y=1.04),
)
st.plotly_chart(fig, width="stretch")

# ---------------- Results ----------------
st.subheader("Natija")
tdf = pd.DataFrame(S.trades)
total = len(tdf)
if total == 0:
    st.caption("Abhi tak koi trade band nahi hua.")
else:
    wins = int((tdf["pips"] > 0).sum())
    losses = int((tdf["pips"] <= 0).sum())
    total_pips = float(tdf["pips"].sum())
    eq = tdf["pips"].cumsum()
    dd = float((eq.cummax() - eq).max())
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total trades", total)
    m2.metric("Win / Loss", f"{wins} / {losses}")
    m3.metric("Win rate", f"{wins / total * 100:.1f}%")
    m4.metric("Total pips", f"{total_pips:.1f}")
    m5.metric("Max drawdown (pips)", f"{dd:.1f}")
    st.dataframe(tdf, width="stretch")
    st.download_button(
        "Trades CSV download karo",
        tdf.to_csv(index=False).encode("utf-8"),
        file_name="my_trades.csv",
        mime="text/csv",
    )
