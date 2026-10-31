# Macro Signal — one verdict: BUY or SELL

A single-page indicator that answers one question, five times:

> **Dollar / Tether — buy or sell?**
> **Gold (global) — buy or sell?**
> **Coin · Emami (سکه امامی) — buy or sell?**
> **Mesghal (مثقال) — buy or sell?**
> **Gold 18k per gram (ایران) — buy or sell?**

Plus a sixth card — the **Gold / Silver ratio** (نسبت طلا به نقره), which tells
you *when* to swap one metal for the other:

| Ratio (XAUUSD ÷ XAGUSD) | Verdict | Meaning |
|-------------------------|---------|---------|
| **> 70** | SELL GOLD / BUY SILVER | طلا بیش‌ازحد گران — تبدیل طلا به نقره |
| **55 – 70** | HOLD | محدوده تعادل — زمان تبدیل نیست |
| **< 55** | BUY GOLD / SELL SILVER | نقره بیش‌ازحد گران — تبدیل نقره به طلا |

And three more cards that round out the board — **Fear & Greed**, **BTC
Dominance** and **BTC ETF Net Flow**:

| Card | Source | Read |
|------|--------|------|
| Fear & Greed | `alternative.me/fng` | ≤ 45 = BUY (fear), ≥ 76 = SELL (greed) |
| BTC Dominance | `coingecko.global` | < 50 = BUY (alt season), > 60 = SELL |
| BTC ETF Net Flow | `farside.co.uk` via `r.jina.ai` | 5-day average: > +$100M = BUY, < −$100M = SELL |

Nine cards, one page, one word each. No charts, no tables, no data dumps.

🔗 **Live:** https://apluscancode.github.io/macro-signal/

---

## How it works

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────┐
│  live feeds  │───▶│ normalized  │───▶│ weighted     │───▶│  BUY/SELL │
│ TradingView  │    │ scores [-1,1]│    │ blend + sign │───▶│   / HOLD  │
│ TGJU / Wallex│    │              │    │ per asset    │    │  + conf%  │
│ CNBC / Binance│   └──────────────┘    └──────────────┘    └───────────┘
│ RSS headlines│                                                            │
└──────────────┘                                                            │
      ▲                                                                     │
      │ GitHub Pages serves the repo; a local cron job regenerates           │
      │ signal.json + market_history.json + iran_gold.json every 30 min      │
      └──────────────────────────────────────────────────────────────────────┘
```

The frontend is a static page that fetches `signal.json`. The Python engine runs
on the server (Hermes cron) — so it can reach APIs that a browser cannot (no CORS
limits), and it never exposes a server.

## Signals used

| Input | Source | Direction (USD / Gold) |
|-------|--------|------------------------|
| USDT premium over free USD | Wallex + TGJU | premium ↑ → sell USD |
| US 10Y yield | CNBC quote service | yield ↑ → buy USD, sell gold |
| Global gold trend (20d + MA20/MA50) | **TradingView** `OANDA:XAUUSD` | gold ↑ → buy gold, buy dollar (toman) |
| Dollar index (DXY) | **TradingView** `TVC:DXY` | DXY ↑ → buy USD, sell gold |
| WTI crude | **TradingView** `TVC:USOIL` | oil ↑ → buy USD (Iran risk premium) |
| Brent crude | **TradingView** `TVC:UKOIL` | oil ↑ → buy USD |
| VIX (fear gauge) | **TradingView** `CBOE:VIX` | fear ↑ → buy USD, buy gold |
| S&P 500 | **TradingView** `SP:SPX` | risk-on ↑ → buy USD |
| BTC 24h | Binance | risk appetite |
| Geopolitical escalation | BBC ME + Al Jazeera + Guardian RSS | war ↑ → buy USD, buy gold |
| **Coin trend** (سکه امامی 20d) | TGJU `sekee` | coin ↑ → buy USD (rial weak) |
| **Mesghal trend** | TGJU `mesghal` | mesghal ↑ → buy USD |
| **Gold-18 trend** | TGJU `geram18` | local gold ↑ |
| **Coin premium momentum** | computed (see below) | premium widening → buy coin |

### Melt value & premium (ارزش ذوب و حاشیه)

The domestic instruments are priced against their intrinsic metal value:

```
gold18_melt  = ounce_usd × usd_toman × (0.75  / 31.1035)      # 18k = 75% purity
mesghal_melt = ounce_usd × usd_toman × (0.705 / 31.1035) × 4.608   # 17k mesghal
coin_melt    = gold18_melt × 8.133                            # Emami = 8.133g of 18k

premium %    = (domestic_price / melt_value − 1) × 100
```

A *rising* premium means more local panic (people bid coins up) → bullish for
the domestic instrument. A *falling* premium means the stress is fading → bearish.

Current readings (Oct 2026): gold 18k **−0.6%** (no premium), mesghal **−0.4%**,
Emami coin **+24%** (the coin premium is the classic coinisation signal).

### Scoring

Each input is normalized to `[-1, +1]`, multiplied by a per-asset sign, then
weighted (weight and sign tables live at the top of `signal_engine.py`):

| Composite score | Verdict |
|-----------------|---------|
| `>= +0.16` | **BUY** |
| `<= -0.16` | **SELL** |
| between | **HOLD** |
| confidence `< 0.30` | **HOLD** (not enough live inputs) |

Confidence is the fraction of total weight that actually had live data — so a
partial feed can never masquerade as a confident signal. The card shows the
confidence plus how many inputs were live (12 for the global assets, 9 for the
domestic ones).

## Verified data sources

| Source | Endpoint | Status |
|--------|----------|--------|
| **TradingView** | websocket via `@mathieuc/tradingview` | ✅ **primary history** — 7 series, 120 daily bars each, no key, no rate limit |
| **TGJU** | `api.tgju.org/v1/market/indicator/summary-table-data/{sym}` | ✅ `sekee` · `sekeb` · `geram18` · `mesghal` — 180 daily rows each |
| Wallex | `api.wallex.ir/v1/markets` | ✅ |
| TGJU main | `tgju.org` (rials → toman ÷10) | ✅ |
| CNBC | `quote.cnbc.com/.../restQuote` | ✅ (US10Y, DXY, oil, gold futures) |
| TwelveData | `api.twelvedata.com/time_series` | ⚠️ secondary — free tier is 8 credits/minute and usually exhausted here |
| Binance | `api.binance.com/api/v3/ticker/24hr` | ✅ |
| BBC / AJ / Guardian | RSS feeds | ✅ |

**Rejected** (tested and failed on this box): Yahoo Finance chart API (timeout),
GDELT doc API (HTTP 429), public CORS proxies (520/522/401 — unreliable).

### TradingView symbols used

```js
OANDA:XAUUSD      gold spot        TVC:DXY         dollar index
TVC:USOIL         WTI crude        TVC:UKOIL       Brent crude
CBOE:VIX          fear gauge       SP:SPX          S&P 500
BINANCE:BTCUSDT   bitcoin
```

`CAPITALCOM:US10Y` does **not** resolve on the free feed — US10Y comes from CNBC.

### TGJU symbol ids (verified Oct 2026)

| Instrument | id | Notes |
|------------|----|-------|
| سکه امامی | `sekee` | the full Emami coin |
| سکه بهار آزاد | `sekeb` | older coin, also tracked |
| طلا ۱۸ (هر گرم) | `geram18` | |
| مثقال | `mesghal` | 4.608g of 17k |

`sekcc` / `seke` / `sekhr` all return HTTP 500 — those are not the right ids.
The list of live ids is visible in the `/profile/*` links on `tgju.org`.

Row format of the TGJU history API (newest first):
`[open, close, high, low, change_html, pct_html, greg_date, shamsi_date]`

## File layout

```
macro-signal/
├── index.html            # five big cards, fetches signal.json
├── style.css
├── signal.json           # generated — committed by the refresh job
├── market_history.json   # generated by fetch_market.js (TradingView)
├── iran_gold.json        # generated by fetch_iran_gold.py (TGJU)
├── signal_engine.py      # the engine
├── fetch_market.js       # TradingView history fetcher (node)
├── fetch_iran_gold.py    # TGJU Iranian-instruments fetcher (python)
├── .github/workflows/refresh-signal.yml
└── README.md
```

## Configuration

The engine reads `TWELVE_DATA_KEY` from the environment. Add it as a repository
secret (`Settings → Secrets → Actions → New secret`) so the workflow can pull
gold history. Without it the engine still runs — it falls back to the CNBC gold
futures quote and records the degradation in `signal.json`.

> **Note on the GitHub Actions workflow:** the file is present in the repo, but
> pushing it requires a PAT with the `workflow` scope. A plain `repo`-scoped
> token is rejected by GitHub. The live page is refreshed by a local Hermes cron
> job instead (`/root/.hermes/scripts/macro_signal_refresh.sh`, every 30 min).

## Run locally

```bash
node fetch_market.js            # refresh market_history.json (TradingView)
python3 fetch_iran_gold.py      # refresh iran_gold.json (TGJU)
python3 signal_engine.py --print # prints the summary, writes signal.json
python3 -m http.server 8000      # then open http://localhost:8000
```

`fetch_market.js` needs `@mathieuc/tradingview` — it is already installed at
`/root/tv-bot/node_modules` (symlinked as `node_modules` in the repo).

## Disclaimer

This is a mechanical indicator, not financial advice. It reads public market and
news data and applies a fixed rule set. Markets can and do move against any
rule-based read — always size your own risk.
