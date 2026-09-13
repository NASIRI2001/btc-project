# BTC-TMN Cross-Exchange Market Data Recorder & Liquidity Analysis

Records BTC-TMN order books and trades from **Wallex**, **Nobitex** and
**Bitpin**, then analyzes liquidity, trading activity, spread and
cross-exchange arbitrage opportunities.

## Files

| File | What it does |
|---|---|
| `record.py` | Polls all three exchanges (order book every 5s, trades every 10s) for a set duration and appends results to `orderbook.csv` / `trades.csv`. |
| `analyze.py` | Reads both CSV files and prints liquidity, spread, activity and arbitrage tables, and saves `spread_chart.png` / `liquidity_chart.png`. |
| `app.py` | Optional interactive Streamlit dashboard version of the same analysis (adjustable band %, adjustable fees, zoomable charts). Not required for the core deliverable. |

## Setup

```bash
pip install requests pandas matplotlib
# only needed for the optional dashboard:
pip install streamlit plotly
```

## Running the recorder (2–4 hours, unattended)

```bash
python record.py
```

Edit `DURATION_HOURS` at the top of the file to control how long it runs
(default: 3). Each exchange call is isolated in its own `try/except`, so a
temporary error on one exchange never stops the other two from recording —
occasional "will retry next loop" messages in the console are expected, not
a bug.

## Running the analysis

```bash
python analyze.py
```

Reads `orderbook.csv` / `trades.csv` from the current folder and prints four
sections (liquidity, spread, trading activity, arbitrage) plus saves two
chart images.

### Optional: interactive dashboard

```bash
streamlit run app.py
```

Opens a browser dashboard where you upload the same two CSV files and can
adjust the liquidity band and fee assumptions live.

## Each exchange's API approach

| Exchange | Order book | Recent trades | Auth |
|---|---|---|---|
| Wallex | `GET api.wallex.ir/v1/depth?symbol=BTCTMN` | `GET api.wallex.ir/v1/trades?symbol=BTCTMN` | None |
| Nobitex | `GET apiv2.nobitex.ir/v3/orderbook/BTCIRT` | `GET apiv2.nobitex.ir/v2/trades/BTCIRT` | None |
| Bitpin | `GET api.bitpin.org/api/v1/mth/orderbook/BTC_IRT/` | `GET api.bitpin.org/api/v1/mth/matches/BTC_IRT/` | None |

All three expose public market data with no API key. A `User-Agent` header
is sent with every request because Bitpin's API returned non-JSON responses
without one.

**Important correction found during development:** despite the `IRT`
("Toman") symbol name, Nobitex's endpoints return prices in **Rial scale** —
confirmed by comparing magnitudes directly against Wallex and Bitpin for the
same market at the same moment (Nobitex was consistently ~10x larger). Both
`get_nobitex_orderbook()` and `get_nobitex_trades()` divide by 10 to correct
this.

## Assumptions

- **Timestamp convention:** every row uses the recorder's own UTC receive
  time, not each exchange's server clock, so all three feeds share one
  clock.
- **Matching non-simultaneous snapshots:** for arbitrage, order books from
  two exchanges are matched by nearest-minute, not exact timestamp.
- **Currency units:** Nobitex values are converted from Rial to Toman
  (÷10) to align with Wallex/Bitpin, which are natively Toman.
- **±1% liquidity:** both BTC quantity and TMN notional are computed, per
  side and combined.
- **Arbitrage realism:** the arbitrage check uses top-of-book prices only
  (not full order-book depth), and does not model transfer time, inventory
  or capital constraints — it answers "was the market mispriced after fees
  at this instant?", not "could this be executed end to end?".
- **Fees used:** 0% Wallex, 0.25% Nobitex, 0.35% Bitpin (published base-tier
  taker fees, configurable at the top of each script).

## Real-world API issues found during development

1. **Nobitex's legacy domain** (`api.nobitex.ir`) stopped resolving mid-test
   — switched to the current `apiv2.nobitex.ir` host and its documented v3
   endpoints.
2. **Bitpin's real base URL** is `api.bitpin.org` (not `api.bitpin.market`,
   which third-party SDK docs pointed to), with an extra `/api/` path
   segment.
3. **Nobitex's Rial/Toman mismatch** described above.
