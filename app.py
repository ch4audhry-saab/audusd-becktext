import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="AUD USD RSI Divergence Backtest", layout="wide")
st.title("AUD USD RSI Divergence Backtest")

# ---------- Sidebar settings ----------
rsi_period = st.sidebar.number_input("RSI period", 5, 50, 14)
swing = st.sidebar.number_input("Swing candles (left/right)", 2, 15, 5)
rr = st.sidebar.number_input("Risk reward", 0.5, 5.0, 2.0, 0.5)
no_trade_start = st.sidebar.number_input("No trade start hour", 0, 23, 20)
no_trade_end = st.sidebar.number_input("No trade end hour", 0, 23, 6)

file = st.sidebar.file_uploader("CSV upload karo (time, open, high, low, close)", type=["csv"])

def calc_rsi(close, period):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def in_no_trade_window(ts):
    h = ts.hour
    if no_trade_start > no_trade_end:
        return h >= no_trade_start or h < no_trade_end
    return no_trade_start <= h < no_trade_end

def find_swings(df, n):
    lows, highs = [], []
    for i in range(n, len(df) - n):
        window = df.iloc[i - n:i + n + 1]
        if df["low"].iloc[i] == window["low"].min():
            lows.append(i)
        if df["high"].iloc[i] == window["high"].max():
            highs.append(i)
    return lows, highs

def run_backtest(df):
    df = df.copy()
    df["rsi"] = calc_rsi(df["close"], rsi_period)
    lows, highs = find_swings(df, swing)
    signals = {}

    # Bullish divergence
    for a, b in zip(lows[:-1], lows[1:]):
        if df["low"].iloc[b] < df["low"].iloc[a] and df["rsi"].iloc[b] > df["rsi"].iloc[a]:
            entry_i = b + swing  # swing confirm hone ke baad entry
            if entry_i < len(df):
                signals[entry_i] = ("BUY", df["low"].iloc[b])

    # Bearish divergence
    for a, b in zip(highs[:-1], highs[1:]):
        if df["high"].iloc[b] > df["high"].iloc[a] and df["rsi"].iloc[b] < df["rsi"].iloc[a]:
            entry_i = b + swing
            if entry_i < len(df):
                signals[entry_i] = ("SELL", df["high"].iloc[b])

    trades = []
    busy_until = -1
    for i in sorted(signals):
        if i <= busy_until:
            continue
        ts = df["time"].iloc[i]
        if in_no_trade_window(ts):
            continue
        side, swing_price = signals[i]
        entry = df["close"].iloc[i]
        if side == "BUY":
            sl = swing_price
            risk = entry - sl
            if risk <= 0:
                continue
            tp = entry + risk * rr
        else:
            sl = swing_price
            risk = sl - entry
            if risk <= 0:
                continue
            tp = entry - risk * rr

        result, exit_i = None, None
        for j in range(i + 1, len(df)):
            hi, lo = df["high"].iloc[j], df["low"].iloc[j]
            if side == "BUY":
                if lo <= sl:
                    result, exit_i = -1.0, j
                    break
                if hi >= tp:
                    result, exit_i = rr, j
                    break
            else:
                if hi >= sl:
                    result, exit_i = -1.0, j
                    break
                if lo <= tp:
                    result, exit_i = rr, j
                    break
        if result is None:
            continue
        busy_until = exit_i
        trades.append({
            "entry_time": ts, "exit_time": df["time"].iloc[exit_i],
            "side": side, "entry": entry, "sl": sl, "tp": tp, "R": result,
        })
    return df, pd.DataFrame(trades)

if file is None:
    st.info("Left side se audusd.csv upload karo.")
    st.stop()

data = pd.read_csv(file)
data.columns = [c.lower().strip() for c in data.columns]
data["time"] = pd.to_datetime(data["time"])
data = data.sort_values("time").reset_index(drop=True)

df, trades = run_backtest(data)

if trades.empty:
    st.warning("Koi trade nahi bana. Data ya settings badal kar dekho.")
    st.stop()

trades["equity_R"] = trades["R"].cumsum()
wins = (trades["R"] > 0).sum()
total = len(trades)
drawdown = (trades["equity_R"].cummax() - trades["equity_R"]).max()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total trades", total)
c2.metric("Win rate", f"{wins / total * 100:.1f}%")
c3.metric("Total R", f"{trades['R'].sum():.1f}")
c4.metric("Max drawdown (R)", f"{drawdown:.1f}")

fig = go.Figure(data=[go.Candlestick(
    x=df["time"], open=df["open"], high=df["high"], low=df["low"], close=df["close"])])
buys = trades[trades["side"] == "BUY"]
sells = trades[trades["side"] == "SELL"]
fig.add_trace(go.Scatter(x=buys["entry_time"], y=buys["entry"], mode="markers",
    marker=dict(symbol="triangle-up", size=12, color="green"), name="BUY"))
fig.add_trace(go.Scatter(x=sells["entry_time"], y=sells["entry"], mode="markers",
    marker=dict(symbol="triangle-down", size=12, color="red"), name="SELL"))
fig.update_layout(height=600, xaxis_rangeslider_visible=False)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Equity curve (R mein)")
st.line_chart(trades.set_index("exit_time")["equity_R"])

st.subheader("Saare trades")
st.dataframe(trades)
