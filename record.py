import requests
import time
import csv
import json
import os
from datetime import datetime, timezone


DURATION_HOURS = 3          # how many hours to record for (task wants 2-4)
POLL_SECONDS = 5            # how often to check order books (seconds)
TRADE_POLL_SECONDS = 10     # how often to check recent trades (seconds)
DEPTH_LEVELS = 20           # how many price levels to save per side

ORDERBOOK_FILE = "orderbook.csv"
TRADES_FILE = "trades.csv"

# Symbols each exchange uses for the BTC-TMN market
WALLEX_SYMBOL = "BTCTMN"
NOBITEX_SYMBOL = "BTCIRT"
BITPIN_SYMBOL = "BTC_IRT"

# Some servers block requests that don't look like they come from a browser.
# Sending a normal-looking User-Agent header avoids that.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def now_iso():
    """Current time as text, always in UTC, so all 3 exchanges share one clock."""
    return datetime.now(timezone.utc).isoformat()




def get_wallex_orderbook():
    r = requests.get("https://api.wallex.ir/v1/depth",
                      params={"symbol": WALLEX_SYMBOL}, headers=HEADERS, timeout=10)
    data = r.json()["result"]
    asks = [[float(a["price"]), float(a["quantity"])] for a in data["ask"][:DEPTH_LEVELS]]
    bids = [[float(b["price"]), float(b["quantity"])] for b in data["bid"][:DEPTH_LEVELS]]
    return asks, bids


def get_nobitex_orderbook():
    r = requests.get(f"https://apiv2.nobitex.ir/v3/orderbook/{NOBITEX_SYMBOL}", headers=HEADERS, timeout=10)
    data = r.json()
    # NOTE: despite the "IRT" (Toman) symbol name, this endpoint's prices are
    # actually in Rial - confirmed by comparing against Wallex/Bitpin, whose
    # prices for the same market were consistently 10x smaller.
    # 1 Toman = 10 Rials, so we divide by 10 here.
    asks = [[float(p) / 10.0, float(q)] for p, q in data["asks"][:DEPTH_LEVELS]]
    bids = [[float(p) / 10.0, float(q)] for p, q in data["bids"][:DEPTH_LEVELS]]
    return asks, bids


def get_bitpin_orderbook():
    r = requests.get(f"https://api.bitpin.org/api/v1/mth/orderbook/{BITPIN_SYMBOL}/", headers=HEADERS, timeout=10)
    data = r.json()
    asks = [[float(p), float(q)] for p, q in data["asks"][:DEPTH_LEVELS]]
    bids = [[float(p), float(q)] for p, q in data["bids"][:DEPTH_LEVELS]]
    return asks, bids




def get_wallex_trades():
    r = requests.get("https://api.wallex.ir/v1/trades",
                      params={"symbol": WALLEX_SYMBOL}, headers=HEADERS, timeout=10)
    trades_raw = r.json()["result"]["latestTrades"]
    trades = []
    for t in trades_raw:
        if t["isBuyOrder"]:
            side = "buy"
        else:
            side = "sell"
        trade = {"price": float(t["price"]), "amount": float(t["quantity"]),
                  "side": side, "time": t["timestamp"]}
        trades.append(trade)
    return trades


def get_nobitex_trades():
    # Same Rial-scale issue as the order book: despite the "IRT" symbol name,
    # prices here are in Rial, confirmed by comparing magnitudes against
    # Wallex/Bitpin. Divide by 10 to convert to Toman.
    r = requests.get(f"https://apiv2.nobitex.ir/v2/trades/{NOBITEX_SYMBOL}", headers=HEADERS, timeout=10)
    data = r.json()
    trades_raw = data if isinstance(data, list) else data.get("trades", [])
    trades = []
    for t in trades_raw:
        amount = t.get("volume", t.get("amount"))
        price_in_toman = float(t["price"]) / 10.0
        trade = {"price": price_in_toman, "amount": float(amount),
                  "side": t.get("type"), "time": t.get("time")}
        trades.append(trade)
    return trades


def get_bitpin_trades():
    r = requests.get(f"https://api.bitpin.org/api/v1/mth/matches/{BITPIN_SYMBOL}/", headers=HEADERS, timeout=10)
    data = r.json()
    if isinstance(data, list):
        trades_raw = data
    else:
        trades_raw = data.get("results", [])

    trades = []
    for t in trades_raw:
        price = t.get("price")
        amount = t.get("base_amount") or t.get("amount")
        side = t.get("side") or t.get("match_side")
        ts = t.get("created_at") or t.get("time")
        if price is not None and amount is not None:
            trade = {"price": float(price), "amount": float(amount), "side": side, "time": ts}
            trades.append(trade)
    return trades




def ensure_files_exist():
    if not os.path.exists(ORDERBOOK_FILE):
        with open(ORDERBOOK_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["time", "exchange", "best_bid", "best_ask", "mid", "asks_json", "bids_json"])
    if not os.path.exists(TRADES_FILE):
        with open(TRADES_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["time", "exchange", "price", "amount", "side"])


def save_orderbook_row(exchange, asks, bids):
    if not asks or not bids:
        return
    best_ask = asks[0][0]
    best_bid = bids[0][0]
    mid = (best_ask + best_bid) / 2.0
    with open(ORDERBOOK_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([now_iso(), exchange, best_bid, best_ask, mid,
                                 json.dumps(asks), json.dumps(bids)])


seen_trades = set()  # so we don't save the same trade twice


def save_new_trades(exchange, trades):
    with open(TRADES_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for t in trades:
            key = f"{exchange}-{t['time']}-{t['price']}-{t['amount']}-{t['side']}"
            if key in seen_trades:
                continue
            seen_trades.add(key)
            writer.writerow([now_iso(), exchange, t["price"], t["amount"], t["side"]])




def poll_all_orderbooks():
    # Wallex
    try:
        asks, bids = get_wallex_orderbook()
        save_orderbook_row("wallex", asks, bids)
    except Exception as e:
        print(f"[wallex] order book error (will retry next loop): {e}")

    # Nobitex
    try:
        asks, bids = get_nobitex_orderbook()
        save_orderbook_row("nobitex", asks, bids)
    except Exception as e:
        print(f"[nobitex] order book error (will retry next loop): {e}")

    # Bitpin
    try:
        asks, bids = get_bitpin_orderbook()
        save_orderbook_row("bitpin", asks, bids)
    except Exception as e:
        print(f"[bitpin] order book error (will retry next loop): {e}")


def poll_all_trades():
    # Wallex
    try:
        trades = get_wallex_trades()
        save_new_trades("wallex", trades)
    except Exception as e:
        print(f"[wallex] trades error (will retry next loop): {e}")

    # Nobitex
    try:
        trades = get_nobitex_trades()
        save_new_trades("nobitex", trades)
    except Exception as e:
        print(f"[nobitex] trades error (will retry next loop): {e}")

    # Bitpin
    try:
        trades = get_bitpin_trades()
        save_new_trades("bitpin", trades)
    except Exception as e:
        print(f"[bitpin] trades error (will retry next loop): {e}")


def main():
    ensure_files_exist()
    print(f"Recording started for {DURATION_HOURS} hours. Press CTRL+C to stop early.")
    print(f"Writing to: {ORDERBOOK_FILE} and {TRADES_FILE}")

    start_time = time.time()
    end_time = start_time + DURATION_HOURS * 3600
    last_trade_poll = 0.0

    while time.time() < end_time:
        loop_start = time.time()

        poll_all_orderbooks()  # every POLL_SECONDS

        if time.time() - last_trade_poll >= TRADE_POLL_SECONDS:
            poll_all_trades()
            last_trade_poll = time.time()

        elapsed_min = (time.time() - start_time) / 60.0
        print(f"... recording, {elapsed_min:.1f} minutes elapsed")

        sleep_left = POLL_SECONDS - (time.time() - loop_start)
        if sleep_left > 0:
            time.sleep(sleep_left)

    print("Done! Recording finished.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user. Whatever was recorded so far is saved and usable.")