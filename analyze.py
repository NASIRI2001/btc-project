import csv
import json
import statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime


FEES = {"wallex": 0.0, "nobitex": 0.0025, "bitpin": 0.0035}
BAND = 0.01  # +-1% around the mid price

ORDERBOOK_FILE = "orderbook.csv"
TRADES_FILE = "trades.csv"
EXCHANGES = ["wallex", "nobitex", "bitpin"]



def load_orderbook_rows():
    rows = []
    with open(ORDERBOOK_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["time"] = datetime.fromisoformat(row["time"])
            row["best_bid"] = float(row["best_bid"])
            row["best_ask"] = float(row["best_ask"])
            row["mid"] = float(row["mid"])
            row["asks"] = json.loads(row["asks_json"])
            row["bids"] = json.loads(row["bids_json"])
            row["spread_pct"] = (row["best_ask"] - row["best_bid"]) / row["mid"] * 100.0
            rows.append(row)
    return rows


def load_trades_rows():
    rows = []
    with open(TRADES_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["time"] = datetime.fromisoformat(row["time"])
            row["price"] = float(row["price"])
            row["amount"] = float(row["amount"])
            rows.append(row)
    return rows




def liquidity_within_band(levels, mid, side):
    btc = 0.0
    if side == "ask":
        limit = mid * (1 + BAND)
    else:
        limit = mid * (1 - BAND)

    for price, qty in levels:
        if side == "ask" and price > limit:
            break
        if side == "bid" and price < limit:
            break
        btc += qty
    return btc


def add_liquidity_to_rows(orderbook_rows):
    for row in orderbook_rows:
        ask_btc = liquidity_within_band(row["asks"], row["mid"], "ask")
        bid_btc = liquidity_within_band(row["bids"], row["mid"], "bid")
        row["total_btc_1pct"] = ask_btc + bid_btc




def group_by_exchange(rows):
    groups = {}
    for ex in EXCHANGES:
        groups[ex] = []
    for row in rows:
        ex = row["exchange"]
        if ex in groups:
            groups[ex].append(row)
    return groups




def print_liquidity_table(ob_by_exchange):
    print("=" * 60)
    print("1) LIQUIDITY (+-1% of mid price) - BTC available, both sides")
    print("=" * 60)
    for ex in EXCHANGES:
        rows = ob_by_exchange[ex]
        values = [r["total_btc_1pct"] for r in rows]
        if not values:
            print(f"{ex:10s}: no data")
            continue
        print(f"{ex:10s}: count={len(values):4d}  median={statistics.median(values):.4f}  "
              f"mean={statistics.mean(values):.4f}  std={statistics.pstdev(values):.4f}")
    print()


def print_spread_table(ob_by_exchange):
    print("=" * 60)
    print("2) SPREAD (%)")
    print("=" * 60)
    for ex in EXCHANGES:
        rows = ob_by_exchange[ex]
        values = [r["spread_pct"] for r in rows]
        if not values:
            print(f"{ex:10s}: no data")
            continue
        print(f"{ex:10s}: count={len(values):4d}  median={statistics.median(values):.4f}  "
              f"mean={statistics.mean(values):.4f}  std={statistics.pstdev(values):.4f}  "
              f"min={min(values):.4f}  max={max(values):.4f}")
    print()


def print_activity_table(trades_by_exchange):
    print("=" * 60)
    print("3) TRADING ACTIVITY")
    print("=" * 60)
    for ex in EXCHANGES:
        rows = trades_by_exchange[ex]
        if not rows:
            print(f"{ex:10s}: no data")
            continue
        times = [r["time"] for r in rows]
        window_hours = (max(times) - min(times)).total_seconds() / 3600.0
        window_hours = max(window_hours, 0.001)  # avoid dividing by zero
        btc_volume = sum(r["amount"] for r in rows)
        print(f"{ex:10s}: {len(rows):4d} trades | {btc_volume:.4f} BTC total | "
              f"{len(rows) / window_hours:6.1f} trades/hour | {btc_volume / window_hours:.4f} BTC/hour")
    print()




def make_spread_chart(ob_by_exchange):
    plt.figure(figsize=(10, 5))
    for ex in EXCHANGES:
        rows = ob_by_exchange[ex]
        times = [r["time"] for r in rows]
        spreads = [r["spread_pct"] for r in rows]
        plt.plot(times, spreads, label=ex, linewidth=0.8)
    plt.legend()
    plt.title("BTC-TMN spread over time (%)")
    plt.xlabel("Time")
    plt.ylabel("Spread %")
    plt.tight_layout()
    plt.savefig("spread_chart.png", dpi=130)
    plt.close()


def make_liquidity_chart(ob_by_exchange):
    plt.figure(figsize=(8, 5))
    data_for_box = []
    for ex in EXCHANGES:
        values = [r["total_btc_1pct"] for r in ob_by_exchange[ex]]
        data_for_box.append(values)
    try:
        plt.boxplot(data_for_box, tick_labels=EXCHANGES, showfliers=False)
    except TypeError:
        plt.boxplot(data_for_box, labels=EXCHANGES, showfliers=False)
    plt.title("Liquidity within +-1% of mid price (BTC)")
    plt.ylabel("BTC")
    plt.tight_layout()
    plt.savefig("liquidity_chart.png", dpi=130)
    plt.close()




def build_minute_prices(ob_by_exchange):
    """For each exchange, build a dictionary: minute -> (best_bid, best_ask)
    using the LAST snapshot seen in that minute."""
    minute_prices = {}
    for ex in EXCHANGES:
        minute_prices[ex] = {}
        for row in ob_by_exchange[ex]:
            minute_key = row["time"].strftime("%Y-%m-%d %H:%M")
            minute_prices[ex][minute_key] = (row["best_bid"], row["best_ask"])
    return minute_prices


def print_arbitrage_table(minute_prices):
    print("=" * 60)
    print("4) ARBITRAGE (top-of-book, matched by nearest minute)")
    print("=" * 60)

    for buy_ex in EXCHANGES:
        for sell_ex in EXCHANGES:
            if buy_ex == sell_ex:
                continue

            profitable_count = 0
            total_count = 0
            best_pct = None
            profitable_pcts = []

            # only check minutes that exist for BOTH exchanges
            common_minutes = set(minute_prices[buy_ex].keys()) & set(minute_prices[sell_ex].keys())

            for minute_key in common_minutes:
                _, buy_ask = minute_prices[buy_ex][minute_key]
                sell_bid, _ = minute_prices[sell_ex][minute_key]

                buy_cost = buy_ask * (1 + FEES[buy_ex])
                sell_revenue = sell_bid * (1 - FEES[sell_ex])
                net_pct = (sell_revenue - buy_cost) / buy_cost * 100.0

                total_count += 1
                if best_pct is None or net_pct > best_pct:
                    best_pct = net_pct
                if net_pct > 0:
                    profitable_count += 1
                    profitable_pcts.append(net_pct)

            if total_count == 0:
                continue

            median_when_profitable = statistics.median(profitable_pcts) if profitable_pcts else 0.0
            pct_of_time = 100 * profitable_count / total_count

            print(f"Buy on {buy_ex:8s} -> Sell on {sell_ex:8s}: "
                  f"profitable {profitable_count:4d}/{total_count:4d} minutes "
                  f"({pct_of_time:5.1f}%), best = {best_pct:.3f}%, "
                  f"median when profitable = {median_when_profitable:.3f}%")
    print()




def main():
    print("Loading data...")
    orderbook_rows = load_orderbook_rows()
    trades_rows = load_trades_rows()
    print(f"Loaded {len(orderbook_rows)} order book snapshots and {len(trades_rows)} trades.\n")

    add_liquidity_to_rows(orderbook_rows)

    ob_by_exchange = group_by_exchange(orderbook_rows)
    trades_by_exchange = group_by_exchange(trades_rows)

    print_liquidity_table(ob_by_exchange)
    print_spread_table(ob_by_exchange)
    print_activity_table(trades_by_exchange)

    make_spread_chart(ob_by_exchange)
    make_liquidity_chart(ob_by_exchange)
    print("Charts saved: spread_chart.png, liquidity_chart.png\n")

    minute_prices = build_minute_prices(ob_by_exchange)
    print_arbitrage_table(minute_prices)

    


if __name__ == "__main__":
    main()