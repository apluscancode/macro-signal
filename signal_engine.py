#!/usr/bin/env python3
"""
Macro Signal Engine — Iran market / geopolitics / economics
=========================================================
One verdict per asset: BUY / SELL / HOLD.

Assets covered
--------------
  dollar    USD & USDT in Toman      (market, macro, geopolitics)
  gold      18k gold gram + ounce  (global + local)
  coin      سکه امامی (Emami coin)
  mesghal   مثقال (17k mesghal)
  gold18    طلا ۱۸ per gram (domestic)

Design rules
------------
* Every source is optional. The engine degrades gracefully and reports which
  inputs were actually available, so a missing feed never fabricates a signal.
* Each input becomes a normalized score in [-1, +1]:
      +1 = strongly bullish (buy)
      -1 = strongly bearish (sell)
  A weighted blend maps to the final verdict.
* Confidence = the fraction of total weight that had live data. A partial feed
  can therefore never masquerade as a confident signal.

Verified sources (tested on this box, 2026-10-20)
---------------------------------------------------
  TradingView  websocket (no key, no limit) — gold, DXY, oil, brent, VIX, SPX, BTC
  Wallex       api.wallex.ir/v1/markets    — USDT/toman, gold ounce
  TGJU         tgju.org + api.tgju.org      — free USD, sekee, sekeb, geram18, mesghal
  CNBC         quote.cnbc.com/.../restQuote — US10Y, .DXY, @CL.1, @GC.1
  TwelveData   api.twelvedata.com           — secondary, 8 credits/min (often spent)
  Binance      api.binance.com              — BTC 24h
  BBC / AJ / Guardian RSS                    — geopolitics headlines
  REJECTED: Yahoo Finance (timeout), GDELT (429), public CORS proxies (520/522/401)

Run:  python3 signal_engine.py            # writes signal.json
      python3 signal_engine.py --print    # human-readable summary
"""
import json
import os
import re
import sys
import gzip
import html
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signal.json")
IRAN_GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iran_gold.json")
TV_HISTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_history.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "application/json,text/html,application/xml,*/*"}
TIMEOUT = 25
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))
TWELVE_KEY = os.environ.get("TWELVE_DATA_KEY", "31da55bb6750499881becd33abae49ca")

# ---------------------------------------------------------------- melt math ---
GRAM_18K = 0.75 / 31.1035       # grams of 18k gold per troy ounce
GRAM_17K = 0.705 / 31.1035
MESGHAL_GRAMS = 4.608          # مثقال = 4.608g of 17k
EMAMI_GRAMS = 8.133            # سکه امامی = 8.133g of 18k

# ------------------------------------------------------------------ weights ---
# Weights per asset; the sign of each input's contribution is separate (the
# D_* tables) so the weight table stays readable.
W_USD = {
    "usdt_wedge": 0.15,     # USDT premium over free USD (premium high = sell)
    "us10y": 0.11,          # rising yields = risk-off = dollar bid
    "gold_trend": 0.09,     # gold up = flight to safety = toman-dollar up
    "dxy": 0.10,            # dollar index
    "oil": 0.07,            # oil up = Iran risk premium
    "brent": 0.04,
    "vix": 0.09,            # fear = dollar bid
    "spx": 0.04,
    "btc": 0.07,
    "iran_escalation": 0.11,  # war = capital flight into USD
    "coin_trend": 0.06,     # coin melting rate up = rial weak
    "mesghal_trend": 0.04,
}
W_GOLD = {
    "usdt_wedge": 0.05,
    "us10y": 0.07,          # inverse
    "gold_trend": 0.20,     # primary driver
    "dxy": 0.10,            # inverse
    "oil": 0.05,
    "brent": 0.03,
    "vix": 0.07,            # fear = safe haven
    "spx": 0.03,
    "btc": 0.05,
    "iran_escalation": 0.15,  # war = gold safe haven
    "coin_trend": 0.08,
    "mesghal_trend": 0.05,
}
# Coin / mesghal / gold18 are domestic: they follow the LOCAL gold trend and
# the local market premium, with the global drivers as secondary context.
W_COIN = {
    "coin_trend": 0.30,        # own trend is the main driver
    "coin_premium": 0.16,     # premium momentum = local stress
    "gold18_trend": 0.13,     # local gold market
    "mesghal_trend": 0.09,
    "usdt_wedge": 0.08,
    "us10y": 0.05,
    "gold_trend": 0.06,
    "iran_escalation": 0.09,
    "vix": 0.04,
}
W_MESHGAL = {
    "mesghal_trend": 0.32,
    "gold18_trend": 0.15,
    "coin_trend": 0.08,
    "usdt_wedge": 0.08,
    "us10y": 0.05,
    "gold_trend": 0.10,
    "iran_escalation": 0.13,
    "vix": 0.05,
    "dxy": 0.04,
}
W_GOLD18 = {
    "gold18_trend": 0.34,
    "mesghal_trend": 0.12,
    "coin_trend": 0.07,
    "usdt_wedge": 0.08,
    "us10y": 0.05,
    "gold_trend": 0.14,
    "iran_escalation": 0.12,
    "vix": 0.05,
    "dxy": 0.03,
}

# sign of each input's contribution per asset
D_USD = {"usdt_wedge": +1, "us10y": -1, "gold_trend": -0.5,
         "dxy": +1, "oil": +0.6, "brent": +0.6, "vix": +0.8,
         "spx": +0.5, "btc": +0.5, "iran_escalation": +1,
         "coin_trend": +0.8, "mesghal_trend": +0.6}
D_GOLD = {"usdt_wedge": -0.3, "us10y": -1, "gold_trend": +1,
          "dxy": -1, "oil": +0.3, "brent": +0.3, "vix": +0.7,
          "spx": -0.4, "btc": +0.3, "iran_escalation": +0.8,
          "coin_trend": +0.7, "mesghal_trend": +0.6}
# premium momentum: a RISING premium means more local panic -> bullish for the
# domestic instrument (people bid coins up); a FALLING premium = the stress is
# fading -> bearish.
D_COIN = {"coin_trend": +1, "coin_premium": +1, "gold18_trend": +0.9,
          "mesghal_trend": +0.7, "usdt_wedge": -0.4, "us10y": -0.8,
          "gold_trend": +0.5, "iran_escalation": +0.7, "vix": +0.4, "dxy": -0.5}
D_MESHGAL = {"mesghal_trend": +1, "gold18_trend": +0.9, "coin_trend": +0.6,
             "usdt_wedge": -0.4, "us10y": -0.8, "gold_trend": +0.6,
             "iran_escalation": +0.7, "vix": +0.4, "dxy": -0.5}
D_GOLD18 = {"gold18_trend": +1, "mesghal_trend": +0.8, "coin_trend": +0.5,
            "usdt_wedge": -0.4, "us10y": -0.8, "gold_trend": +0.7,
            "iran_escalation": +0.7, "vix": +0.4, "dxy": -0.5}

ESCALATION = {
    "attack": 2, "strike": 2, "airstrike": 3, "missile": 2, "drone": 1,
    "nuclear": 3, "enrichment": 2, "sanction": 1, "war": 2, "escalat": 2,
    "hormuz": 3, "retaliat": 2, "invasion": 3, "explosion": 2, "coup": 2,
    "blockade": 2, "shutdown": 2, "threat": 1, "ultimatum": 2, "seize": 1,
}
DEESCALATION = {
    "ceasefire": 3, "truce": 3, "agreement": 2, "peace": 3, "diplomat": 1,
    "negotiat": 1, "easing": 1, "reopen": 2, "resolved": 2, "de-escalat": 3,
    "amnesty": 1, "pact": 2, "accord": 2, "withdraw": 2, "easing tensions": 3,
}
NEGATIVE_CONTEXT = ("stock market", "s&p", "nasdaq", "dow jones", "tech stocks",
                    "earnings", "layoff", "strike action")


def _get(url, timeout=TIMEOUT, headers=None):
    h = dict(UA)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        enc = (r.headers.get("Content-Encoding") or "").lower()
        if enc == "gzip" or data[:2] == b"\x1f\x8b":
            try:
                data = gzip.decompress(data)
            except OSError:
                pass
    return data.decode("utf-8", "ignore")


def _num(v, default=None):
    try:
        return float(str(v).replace(",", "").replace("٬", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def clamp(x):
    return max(-1.0, min(1.0, x))


# ------------------------------------------------------------------ Wallex ---
def fetch_wallex():
    out = {"ok": False}
    try:
        d = json.loads(_get("https://api.wallex.ir/v1/markets"))
        syms = d["result"]["symbols"]
        st = syms["USDTTMN"]["stats"]
        out["usdt_toman"] = float(st["lastPrice"])
        out["usdt_bid"] = _num(st.get("bidPrice"))
        out["usdt_ask"] = _num(st.get("askPrice"))
        if "XAUTTMN" in syms:
            out["gold_oz_toman"] = float(syms["XAUTTMN"]["stats"]["lastPrice"])
        out["ok"] = True
    except Exception as e:
        out["error"] = f"wallex: {type(e).__name__}: {e}"
    return out


# -------------------------------------------------------------------- TGJU ---
def fetch_tgju():
    out = {"ok": False}
    try:
        page = _get("https://www.tgju.org/")
        found = {}
        for m in re.finditer(r"<li[^>]*>(.*?)</li>", page, re.S):
            block = m.group(1)
            t = re.search(r"<h3[^>]*>(.*?)</h3>", block, re.S)
            v = re.search(r"span[^>]*class=\"info-value\"[^>]*>(.*?)</span>", block, re.S)
            if not (t and v):
                continue
            label = re.sub(r"<[^>]+>", "", t.group(1)).strip()
            val = _num(re.sub(r"[^0-9.]", "", re.sub(r"<[^>]+>", "", v.group(1))))
            if val is None:
                continue
            if "دلار" in label and "usd_toman" not in found:
                found["usd_toman"] = val / 10.0 if val > 100000 else val
            elif "تتر" in label and "usdt_toman" not in found:
                found["usdt_toman"] = val / 10.0 if val > 100000 else val
            elif ("طلا ۱۸" in label or "طلا18" in label) and "gold18_toman" not in found:
                found["gold18_toman"] = val / 10.0 if val > 100000 else val
            elif "مثقال" in label and "mesghal_toman" not in found:
                found["mesghal_toman"] = val / 10.0 if val > 100000 else val
            elif "سکه" in label and "coin_full_toman" not in found:
                found["coin_full_toman"] = val / 10.0 if val > 100000 else val
        out.update(found)
        out["ok"] = "usd_toman" in found
    except Exception as e:
        out["error"] = f"tgju: {type(e).__name__}: {e}"
    return out


# -------------------------------------------------------------------- CNBC ---
CNBC = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
        "?symbols={sym}&requestMethod=quick&partnerId=2&fund=1&exthrs=1&output=json")


def fetch_cnbc(symbols):
    out = {}
    for label, sym in symbols.items():
        try:
            d = json.loads(_get(CNBC.format(sym=urllib.parse.quote(sym, safe=""))))
            q = (d.get("FormattedQuoteResult", {}).get("FormattedQuote") or [{}])[0]
            last = _num(q.get("last"))
            chg_pct = _num(q.get("change_pct"))
            if chg_pct is None:
                abschg = _num(q.get("change"))
                prev = _num(q.get("previous_day_closing"))
                if abschg is not None and prev:
                    chg_pct = (abschg / prev) * 100
            out[label] = {"last": last, "change_pct": chg_pct,
                          "change": _num(q.get("change")),
                          "prev_close": _num(q.get("previous_day_closing")),
                          "name": q.get("name"), "time": q.get("last_time")}
        except Exception:
            out[label] = None
    return out


# --------------------------------------------------------------- local files ---
def load_json(path, key=None):
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            d = json.load(f)
        return d.get(key) if key else d
    except Exception:
        return None


def series_block(closes):
    if not closes or len(closes) < 6:
        return None
    last = closes[0]
    def chg(n):
        return (last / closes[n] - 1) * 100 if len(closes) > n else None
    ma20 = sum(closes[:20]) / min(20, len(closes))
    ma50 = sum(closes[:50]) / min(50, len(closes))
    return {
        "last": last,
        "chg_5d_pct": chg(5), "chg_20d_pct": chg(20), "chg_60d_pct": chg(60),
        "ma20": ma20, "ma50": ma50,
        "above_ma20": last > ma20, "above_ma50": last > ma50,
        "n": len(closes),
    }


def quote_block(cnbc_row):
    if not cnbc_row or cnbc_row.get("last") is None:
        return None
    chg = cnbc_row.get("change_pct")
    return {"last": cnbc_row["last"], "chg_5d_pct": chg, "chg_20d_pct": None,
            "chg_60d_pct": None, "ma20": None, "ma50": None,
            "above_ma20": None, "above_ma50": None, "n": 1}


def fetch_twelvedata(symbol, days=90):
    url = ("https://api.twelvedata.com/time_series"
           f"?symbol={urllib.parse.quote(symbol, safe='')}&interval=1day"
           f"&outputsize={days}&apikey={TWELVE_KEY}")
    try:
        d = json.loads(_get(url))
        if d.get("status") == "error":
            return None
        closes = [float(v["close"]) for v in d.get("values", []) if v.get("close")]
        return closes if len(closes) >= 15 else None
    except Exception:
        return None


# ------------------------------------------------------------------ Binance ---
def fetch_binance():
    # GitHub Actions runners are sometimes geo-blocked by api.binance.com, so
    # try the mirror hosts too.
    hosts = [
        "https://api.binance.com",
        "https://api1.binance.com",
        "https://data-api.binance.vision",
    ]
    for host in hosts:
        try:
            d = json.loads(_get(f"{host}/api/v3/ticker/24hr?symbol=BTCUSDT"))
            last = _num(d.get("lastPrice"))
            chg = _num(d.get("priceChangePercent"))
            if last:
                return {"last": last, "chg_24h_pct": chg, "host": host}
        except Exception:
            continue
    return None


# ----------------------------------------------------------------- Headlines ---
RSS_FEEDS = [
    ("BBC Middle East", "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("Guardian Iran", "https://www.theguardian.com/world/iran/rss"),
]
IRAN_HINTS = ("iran", "iranian", "tehran", "hezbollah", "houthi", "yemen",
              "irgc", "natanz", "fordow", "strait of hormuz", "persian gulf",
              "hamid rezaei", "iaea")


def fetch_headlines():
    titles, ok = [], False
    for name, url in RSS_FEEDS:
        try:
            xml = _get(url, timeout=18)
            for it in re.findall(r"<title[^>]*>(.*?)</title>", xml, re.S | re.I):
                t = html.unescape(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", it)).strip()
                if not t or (t.lower().startswith("bbc") and len(t) < 25):
                    continue
                if any(h in t.lower() for h in IRAN_HINTS):
                    titles.append(t)
            if titles:
                ok = True
        except Exception:
            continue

    hits = degrade = 0
    scored = []
    for t in titles:
        low = t.lower()
        if any(n in low for n in NEGATIVE_CONTEXT):
            continue
        s = 0
        for w, wt in ESCALATION.items():
            if w in low:
                s += wt
        for w, wt in DEESCALATION.items():
            if w in low:
                s -= wt
        if s > 0:
            hits += s
        elif s < 0:
            degrade += abs(s)
        scored.append((s, t))

    if hits + degrade == 0:
        return {"score": 0.0, "ok": ok, "n_titles": len(titles),
                "escalation_hits": hits, "deescalation_hits": degrade, "top": []}
    net = (hits - degrade) / float(hits + degrade)
    return {"score": clamp(net), "ok": ok, "n_titles": len(titles),
            "escalation_hits": hits, "deescalation_hits": degrade,
            "top": [t for _, t in sorted(scored, key=lambda x: -x[0])[:4]]}


# ------------------------------------------------------------------ Scorers ---
def s_wedge(wallex, tgju):
    u = wallex.get("usdt_toman") or tgju.get("usdt_toman")
    fx = tgju.get("usd_toman")
    if not u or not fx or fx <= 0:
        return None, None
    prem = (u / fx - 1.0) * 100
    return clamp(-prem / 7.0), prem


def s_trend(b, key="chg_20d_pct"):
    if not b or b.get(key) is None:
        return None
    return clamp(b[key] / 12.0)


def s_ma(b):
    if not b or b.get("above_ma20") is None:
        return None
    return (0.5 if b["above_ma20"] else -0.5) + (0.5 if b["above_ma50"] else -0.5)


def blend(*parts):
    parts = [p for p in parts if p is not None]
    return sum(parts) / len(parts) if parts else None


def s_yield(cnbc_y):
    if not cnbc_y or cnbc_y.get("change_pct") is None:
        return None
    return clamp(-cnbc_y["change_pct"] / 1.2)


def s_btc(b):
    if not b or b.get("chg_24h_pct") is None:
        return None
    return clamp(b["chg_24h_pct"] / 6.0)


def s_premium_momentum(premium_now, premium_ref):
    """Score the change in a domestic premium vs its reference value."""
    if premium_now is None or premium_ref is None:
        return None
    d = premium_now - premium_ref
    return clamp(d / 6.0)      # +6pp premium change -> +1.0


# --------------------------------------------------------------- melt/premium ---
def melt_values(oz_usd, usd_toman):
    """Melt (intrinsic) values in Toman for the domestic instruments."""
    if not oz_usd or not usd_toman:
        return {}
    g18 = oz_usd * usd_toman * GRAM_18K
    mesg = oz_usd * usd_toman * GRAM_17K * MESGHAL_GRAMS
    coin = g18 * EMAMI_GRAMS
    return {"gold18": g18, "mesghal": mesg, "coin_emami": coin}


# ------------------------------------------------------------------- Build ---
def build_signal():
    errors = []

    wallex = fetch_wallex()
    if not wallex.get("ok"):
        errors.append(wallex.get("error", "wallex failed"))
    tgju = fetch_tgju()
    if not tgju.get("ok"):
        errors.append(tgju.get("error", "tgju failed"))

    cnbc = fetch_cnbc({"us10y": "US10Y", "dxy": ".DXY", "oil": "@CL.1", "gold_fut": "@GC.1"})

    # --- global history (TradingView primary, TwelveData secondary) ---
    gold_block = None
    gold_closes = fetch_twelvedata("XAU/USD", 90)
    if gold_closes:
        gold_block = series_block(gold_closes)
    if not gold_block:
        gold_block = quote_block(cnbc.get("gold_fut"))

    tv = load_json(TV_HISTORY, "series") or {}
    if not tv:
        errors.append("tradingview history missing — run fetch_market.js")
    dxy_block = oil_block = brent_block = vix_block = spx_block = btc_tv = None
    if tv:
        gold_block = dict(tv["gold"]) if tv.get("gold") else gold_block
        dxy_block = dict(tv["dxy"]) if tv.get("dxy") else None
        oil_block = dict(tv["oil"]) if tv.get("oil") else None
        brent_block = dict(tv["brent"]) if tv.get("brent") else None
        vix_block = dict(tv["vix"]) if tv.get("vix") else None
        spx_block = dict(tv["spx"]) if tv.get("spx") else None
        btc_tv = dict(tv["btc"]) if tv.get("btc") else None
    if not dxy_block:
        dxy_block = quote_block(cnbc.get("dxy"))
    if not oil_block:
        oil_block = quote_block(cnbc.get("oil"))

    # --- Iranian gold instruments (TGJU history) ---
    ig = load_json(IRAN_GOLD, "instruments") or {}
    if not ig:
        errors.append("iran_gold.json missing — run fetch_iran_gold.py")
    coin = ig.get("coin_emami")
    coin_bahar = ig.get("coin_bahar")
    gold18 = ig.get("gold18")
    mesghal = ig.get("mesghal")

    binance = fetch_binance()
    if not binance:
        # not fatal — the engine falls back to the TradingView BTC series
        errors.append("binance unavailable (using TradingView BTC fallback)")

    head = fetch_headlines()
    if not head.get("ok"):
        errors.append("headline feeds unavailable")

    # --- melt / premium ---
    oz_usd = (gold_block or {}).get("last")
    usd_toman = tgju.get("usd_toman")
    melts = melt_values(oz_usd, usd_toman)
    prem = {}
    for key, melt in melts.items():
        px = None
        if key == "coin_emami" and coin:
            px = coin.get("last")
        elif key == "mesghal" and mesghal:
            px = mesghal.get("last")
        elif key == "gold18" and gold18:
            px = gold18.get("last")
        prem[key] = round((px / melt - 1) * 100, 2) if (px and melt) else None

    # reference premium 20 trading days ago — recomputed from the trend ratio
    def prem_ref(key, series_key):
        blk = {"coin_emami": coin, "mesghal": mesghal, "gold18": gold18}.get(key)
        if not blk or not melts.get(key):
            return None
        c20 = blk.get("chg_20d_pct")
        if c20 is None:
            return None
        # price 20 days ago = last / (1 + c20/100); melt moves with the dollar,
        # approximated by the global gold move over the same window
        px_old = blk["last"] / (1 + c20 / 100.0)
        g20 = (gold_block or {}).get("chg_20d_pct")
        melt_old = melts[key] / (1 + (g20 or 0) / 100.0)
        if not melt_old:
            return None
        return (px_old / melt_old - 1) * 100

    prem_refs = {k: prem_ref(k, None) for k in ("coin_emami", "mesghal", "gold18")}

    # --- input scores ---
    wedge_s, wedge_prem = s_wedge(wallex, tgju)
    gold_trend = blend(s_trend(gold_block, "chg_20d_pct"),
                       s_trend(gold_block, "chg_5d_pct"), s_ma(gold_block))
    dxy_s = blend(s_trend(dxy_block, "chg_20d_pct"),
                  s_trend(dxy_block, "chg_5d_pct"), s_ma(dxy_block))
    oil_s = blend(s_trend(oil_block, "chg_20d_pct"),
                  s_trend(oil_block, "chg_5d_pct"), s_ma(oil_block))
    brent_s = blend(s_trend(brent_block, "chg_20d_pct"),
                    s_trend(brent_block, "chg_5d_pct"), s_ma(brent_block))
    vix_s = s_trend(vix_block, "chg_20d_pct") or s_trend(vix_block, "chg_5d_pct")
    spx_s = blend(s_trend(spx_block, "chg_20d_pct"), s_ma(spx_block))
    btc_s = s_btc(binance)
    if btc_s is None and btc_tv:
        btc_s = blend(s_trend(btc_tv, "chg_20d_pct"), s_trend(btc_tv, "chg_5d_pct"))
    y10_s = s_yield(cnbc.get("us10y"))
    esc_s = head.get("score") if head.get("ok") else None

    coin_trend = blend(s_trend(coin, "chg_20d_pct"),
                       s_trend(coin, "chg_5d_pct"), s_ma(coin)) if coin else None
    mesghal_trend = blend(s_trend(mesghal, "chg_20d_pct"),
                          s_trend(mesghal, "chg_5d_pct"), s_ma(mesghal)) if mesghal else None
    gold18_trend = blend(s_trend(gold18, "chg_20d_pct"),
                         s_trend(gold18, "chg_5d_pct"), s_ma(gold18)) if gold18 else None
    coin_prem = s_premium_momentum(prem.get("coin_emami"), prem_refs.get("coin_emami"))

    inputs = {
        "usdt_wedge": wedge_s, "us10y": y10_s, "gold_trend": gold_trend,
        "dxy": dxy_s, "oil": oil_s, "brent": brent_s, "vix": vix_s,
        "spx": spx_s, "btc": btc_s, "iran_escalation": esc_s,
        "coin_trend": coin_trend, "mesghal_trend": mesghal_trend,
        "gold18_trend": gold18_trend, "coin_premium": coin_prem,
    }

    def aggregate(weights, deltas):
        acc = tot = 0.0
        used = []
        for k, w in weights.items():
            v = inputs.get(k)
            if v is None:
                continue
            acc += (v * deltas.get(k, 1.0)) * w
            tot += w
            used.append(k)
        return (acc / tot if tot else 0.0), tot, used

    ASSETS = [
        ("asset_dollar", "Dollar / Tether", W_USD, D_USD),
        ("asset_gold", "Gold (ounce + 18k)", W_GOLD, D_GOLD),
        ("asset_coin", "Coin (Emami)", W_COIN, D_COIN),
        ("asset_meshgal", "Mesghal", W_MESHGAL, D_MESHGAL),
        ("asset_gold18", "Gold 18k (per gram)", W_GOLD18, D_GOLD18),
    ]

    def verdict(score, conf, thr=0.16):
        if conf < 0.30:
            return "HOLD", "not enough live inputs"
        if score >= thr:
            return "BUY", f"score {score:+.2f}"
        if score <= -thr:
            return "SELL", f"score {score:+.2f}"
        return "HOLD", f"score {score:+.2f}"

    now = datetime.now(IRAN_TZ)
    out = {
        "generated_at": now.isoformat(),
        "generated_at_display": now.strftime("%Y-%m-%d %H:%M") + " Iran",
    }
    for key, label, W, D in ASSETS:
        score, conf, used = aggregate(W, D)
        v, why = verdict(score, conf)
        out[key] = {
            "label": label, "verdict": v, "score": round(score, 3),
            "confidence": round(conf, 2), "reason": why,
            "inputs_used": used, "inputs_total": len(W),
        }

    out["raw"] = {
        "usdt_toman": wallex.get("usdt_toman"),
        "usd_free_toman": tgju.get("usd_toman"),
        "usdt_premium_pct": round(wedge_prem, 2) if wedge_prem is not None else None,
        "gold_oz_usd": oz_usd,
        "gold_20d_pct": round(gold_block["chg_20d_pct"], 2) if gold_block and gold_block.get("chg_20d_pct") is not None else None,
        "us10y": cnbc.get("us10y", {}).get("last") if cnbc.get("us10y") else None,
        "dxy": dxy_block.get("last") if dxy_block else None,
        "oil": oil_block.get("last") if oil_block else None,
        "brent": brent_block.get("last") if brent_block else None,
        "vix": vix_block.get("last") if vix_block else None,
        "vix_20d_pct": round(vix_block["chg_20d_pct"], 2) if vix_block and vix_block.get("chg_20d_pct") is not None else None,
        "spx": spx_block.get("last") if spx_block else None,
        "btc": binance.get("last") if binance else (btc_tv.get("last") if btc_tv else None),
        "coin_emami_toman": coin.get("last") if coin else None,
        "coin_emami_20d_pct": coin.get("chg_20d_pct") if coin else None,
        "coin_premium_pct": prem.get("coin_emami"),
        "coin_premium_20d_ago_pct": round(prem_refs["coin_emami"], 2) if prem_refs.get("coin_emami") is not None else None,
        "mesghal_toman": mesghal.get("last") if mesghal else None,
        "mesghal_20d_pct": mesghal.get("chg_20d_pct") if mesghal else None,
        "mesghal_premium_pct": prem.get("mesghal"),
        "gold18_toman": gold18.get("last") if gold18 else None,
        "gold18_20d_pct": gold18.get("chg_20d_pct") if gold18 else None,
        "gold18_premium_pct": prem.get("gold18"),
        "coin_bahar_toman": coin_bahar.get("last") if coin_bahar else None,
        "melt_gold18_toman": round(melts.get("gold18"), 0) if melts.get("gold18") else None,
        "melt_coin_toman": round(melts.get("coin_emami"), 0) if melts.get("coin_emami") else None,
        "melt_meshgal_toman": round(melts.get("mesghal"), 0) if melts.get("mesghal") else None,
        "escalation_score": round(head.get("score"), 3) if head.get("ok") else None,
        "headlines_scanned": head.get("n_titles", 0),
    }
    out["headline_samples"] = head.get("top", [])
    out["errors"] = errors
    return out


def main():
    sig = build_signal()
    with open(OUT, "w") as f:
        json.dump(sig, f, indent=2, ensure_ascii=False)
    if "--print" in sys.argv:
        print("=" * 70)
        for k in ("asset_dollar", "asset_gold", "asset_coin", "asset_meshgal", "asset_gold18"):
            a = sig[k]
            print(f"  {a['label']:<24} {a['verdict']:<5} score={a['score']:+.3f}  "
                  f"conf={a['confidence']:.0%}  [{len(a['inputs_used'])}/{a['inputs_total']} inputs]")
        print(f"  {sig['generated_at_display']}")
        print("=" * 70)
        for k, v in sig["raw"].items():
            print(f"  {k:<26} {v}")
        if sig["errors"]:
            print("  ERRORS:", sig["errors"])
        print("  HEADLINES:")
        for t in sig["headline_samples"]:
            print("   -", t[:92])
    else:
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
