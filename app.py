"""
Interactive dashboard for the BTC-TMN cross-exchange analysis.

This is a companion to analyze.py, not a replacement for it: analyze.py
stays the simple, dependency-light script used for the actual submission.
This file is an optional, nicer way to *explore* the same data interactively
(zoomable charts, adjustable parameters) using Streamlit + pandas + Plotly.

Run with:
    pip install streamlit pandas plotly
    streamlit run app.py
"""

import json
import itertools
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ============================================================
#  PAGE SETUP
# ============================================================
st.set_page_config(page_title="تحلیل بازار BTC-TMN", layout="wide")

st.title("داشبورد تحلیل نقدینگی بازار BTC-TMN")
st.caption("والکس · نوبیتکس · بیت‌پین — داده‌ی جمع‌آوری‌شده توسط record.py")

EXCHANGES = ["wallex", "nobitex", "bitpin"]
EXCHANGE_COLORS = {"wallex": "#1f77b4", "nobitex": "#ff7f0e", "bitpin": "#2ca02c"}


# ============================================================
#  SIDEBAR — FILE UPLOAD + ADJUSTABLE PARAMETERS
# ============================================================
st.sidebar.header("داده‌ی ورودی")
ob_file = st.sidebar.file_uploader("فایل orderbook.csv", type="csv")
tr_file = st.sidebar.file_uploader("فایل trades.csv", type="csv")

st.sidebar.header("پارامترهای قابل‌تنظیم")
band_pct = st.sidebar.slider(
    "بازه‌ی نقدینگی (± درصد حوالی قیمت میانی)",
    min_value=0.1, max_value=5.0, value=1.0, step=0.1,
) / 100.0

st.sidebar.caption("کارمزد هر صرافی (درصد، برای محاسبه‌ی آربیتراژ)")
fee_wallex = st.sidebar.number_input("کارمزد Wallex (%)", value=0.0, step=0.05) / 100.0
fee_nobitex = st.sidebar.number_input("کارمزد Nobitex (%)", value=0.25, step=0.05) / 100.0
fee_bitpin = st.sidebar.number_input("کارمزد Bitpin (%)", value=0.35, step=0.05) / 100.0
FEES = {"wallex": fee_wallex, "nobitex": fee_nobitex, "bitpin": fee_bitpin}

if ob_file is None or tr_file is None:
    st.info(
        "برای دیدن داشبورد، فایل‌های **orderbook.csv** و **trades.csv** را که "
        "record.py تولید کرده، از نوار کناری آپلود کنید."
    )
    st.stop()


# ============================================================
#  LOAD + PREP DATA (cached so sliders don't re-read the CSV every time)
# ============================================================
@st.cache_data
def load_orderbook(file):
    df = pd.read_csv(file)
    df["time"] = pd.to_datetime(df["time"])
    df["asks"] = df["asks_json"].apply(json.loads)
    df["bids"] = df["bids_json"].apply(json.loads)
    df["spread_pct"] = (df["best_ask"] - df["best_bid"]) / df["mid"] * 100.0
    return df


@st.cache_data
def load_trades(file):
    df = pd.read_csv(file)
    df["time"] = pd.to_datetime(df["time"])
    return df


def liquidity_within_band(levels, mid, side, band):
    limit = mid * (1 + band) if side == "ask" else mid * (1 - band)
    btc = 0.0
    for price, qty in levels:
        if side == "ask" and price > limit:
            break
        if side == "bid" and price < limit:
            break
        btc += qty
    return btc


@st.cache_data
def add_liquidity(df, band):
    ask_btc = df.apply(lambda r: liquidity_within_band(r["asks"], r["mid"], "ask", band), axis=1)
    bid_btc = df.apply(lambda r: liquidity_within_band(r["bids"], r["mid"], "bid", band), axis=1)
    out = df.copy()
    out["total_btc"] = ask_btc + bid_btc
    return out


orderbook_df = load_orderbook(ob_file)
trades_df = load_trades(tr_file)
orderbook_df = add_liquidity(orderbook_df, band_pct)

st.success(
    f"{len(orderbook_df):,} اسنپ‌شات دفتر سفارش و {len(trades_df):,} معامله بارگذاری شد "
    f"(بازه‌ی نقدینگی فعلی: ±{band_pct*100:.1f}٪)"
)


# ============================================================
#  TABS
# ============================================================
tab_overview, tab_liquidity, tab_spread, tab_activity, tab_arbitrage = st.tabs(
    ["نمای کلی", "نقدینگی", "اسپرد", "فعالیت معاملاتی", "آربیتراژ"]
)


# ---------- OVERVIEW ----------
with tab_overview:
    cols = st.columns(3)
    for col, ex in zip(cols, EXCHANGES):
        sub = orderbook_df[orderbook_df["exchange"] == ex]
        with col:
            st.metric(f"{ex} — میانه‌ی نقدینگی (BTC)", f"{sub['total_btc'].median():.3f}")
            st.metric(f"{ex} — میانه‌ی اسپرد (%)", f"{sub['spread_pct'].median():.3f}%")

    st.divider()
    fig = go.Figure()
    for ex in EXCHANGES:
        sub = orderbook_df[orderbook_df["exchange"] == ex]
        fig.add_trace(go.Scatter(x=sub["time"], y=sub["mid"], mode="lines", name=ex, line=dict(color=EXCHANGE_COLORS[ex])))
    fig.update_layout(title="قیمت میانی در طول زمان (تومان)", height=420)
    st.plotly_chart(fig, use_container_width=True)


# ---------- LIQUIDITY ----------
with tab_liquidity:
    st.subheader(f"نقدینگی در بازه‌ی ±{band_pct*100:.1f}٪ حوالی قیمت میانی")

    summary = orderbook_df.groupby("exchange")["total_btc"].agg(
        count="count", median="median", mean="mean", std="std"
    ).reindex(EXCHANGES)
    st.dataframe(summary.style.format("{:.4f}", subset=["median", "mean", "std"]), use_container_width=True)

    fig = px.box(orderbook_df, x="exchange", y="total_btc", color="exchange",
                 color_discrete_map=EXCHANGE_COLORS, points="outliers",
                 category_orders={"exchange": EXCHANGES})
    fig.update_layout(title="توزیع نقدینگی هر صرافی", showlegend=False, height=480)
    st.plotly_chart(fig, use_container_width=True)


# ---------- SPREAD ----------
with tab_spread:
    st.subheader("اسپرد (فاصله‌ی قیمت خرید و فروش)")

    summary = orderbook_df.groupby("exchange")["spread_pct"].agg(
        count="count", median="median", mean="mean", std="std", min="min", max="max"
    ).reindex(EXCHANGES)
    st.dataframe(summary.style.format("{:.4f}", subset=["median", "mean", "std", "min", "max"]), use_container_width=True)

    fig = go.Figure()
    for ex in EXCHANGES:
        sub = orderbook_df[orderbook_df["exchange"] == ex]
        fig.add_trace(go.Scatter(x=sub["time"], y=sub["spread_pct"], mode="lines",
                                  name=ex, line=dict(color=EXCHANGE_COLORS[ex], width=1)))
    fig.update_layout(title="اسپرد در طول زمان (%) — قابل زوم و هاور", height=480,
                       yaxis_title="Spread %", xaxis_title="زمان")
    st.plotly_chart(fig, use_container_width=True)


# ---------- ACTIVITY ----------
with tab_activity:
    st.subheader("فعالیت معاملاتی")

    rows = []
    for ex in EXCHANGES:
        sub = trades_df[trades_df["exchange"] == ex]
        if sub.empty:
            continue
        window_hours = max((sub["time"].max() - sub["time"].min()).total_seconds() / 3600.0, 0.001)
        rows.append({
            "exchange": ex,
            "trades": len(sub),
            "btc_volume": sub["amount"].sum(),
            "trades_per_hour": len(sub) / window_hours,
            "btc_per_hour": sub["amount"].sum() / window_hours,
        })
    activity_df = pd.DataFrame(rows).set_index("exchange").reindex(EXCHANGES)
    st.dataframe(activity_df.style.format("{:.3f}", subset=["btc_volume", "trades_per_hour", "btc_per_hour"]),
                 use_container_width=True)

    fig = px.bar(activity_df.reset_index(), x="exchange", y="trades_per_hour", color="exchange",
                 color_discrete_map=EXCHANGE_COLORS, category_orders={"exchange": EXCHANGES})
    fig.update_layout(title="معامله در ساعت", showlegend=False, height=420)
    st.plotly_chart(fig, use_container_width=True)


# ---------- ARBITRAGE ----------
with tab_arbitrage:
    st.subheader("آربیتراژ بین‌صرافی‌ای (بالای دفتر سفارش، پس از کارمزد)")
    st.caption("تطبیق بر اساس نزدیک‌ترین دقیقه‌ی مشترک بین دو صرافی — یک سنجه‌ی تئوریک، نه یک استراتژی اجراپذیر اثبات‌شده.")

    ob = orderbook_df.copy()
    ob["minute"] = ob["time"].dt.floor("min")
    last_per_minute = ob.sort_values("time").groupby(["exchange", "minute"]).last().reset_index()

    pivot_bid = last_per_minute.pivot(index="minute", columns="exchange", values="best_bid")
    pivot_ask = last_per_minute.pivot(index="minute", columns="exchange", values="best_ask")

    arb_rows = []
    for buy_ex, sell_ex in itertools.permutations(EXCHANGES, 2):
        if buy_ex not in pivot_ask.columns or sell_ex not in pivot_bid.columns:
            continue
        buy_cost = pivot_ask[buy_ex] * (1 + FEES[buy_ex])
        sell_revenue = pivot_bid[sell_ex] * (1 - FEES[sell_ex])
        net_pct = ((sell_revenue - buy_cost) / buy_cost * 100.0).dropna()
        if net_pct.empty:
            continue
        profitable = net_pct[net_pct > 0]
        arb_rows.append({
            "direction": f"{buy_ex} \u2192 {sell_ex}",
            "minutes_checked": len(net_pct),
            "pct_profitable": 100 * len(profitable) / len(net_pct),
            "best_net_pct": net_pct.max(),
            "median_when_profitable": profitable.median() if len(profitable) else 0.0,
        })

    arb_df = pd.DataFrame(arb_rows).sort_values("pct_profitable", ascending=False)
    st.dataframe(
        arb_df.style.format({
            "pct_profitable": "{:.1f}%", "best_net_pct": "{:.3f}%", "median_when_profitable": "{:.3f}%",
        }),
        use_container_width=True, hide_index=True,
    )

    fig = px.bar(arb_df, x="direction", y="pct_profitable",
                 title="درصد دقایقی که هر جهت سودآور بود")
    fig.update_layout(height=420, yaxis_title="% زمان سودآور", xaxis_title="")
    st.plotly_chart(fig, use_container_width=True)
