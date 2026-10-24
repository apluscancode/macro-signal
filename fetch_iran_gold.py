#!/usr/bin/env python3
"""
Iranian gold instruments — history + melt-value / premium analysis.

Sources
-------
TGJU summary-table API (no key):
    https://api.tgju.org/v1/market/indicator/summary-table-data/{symbol}
    Row layout (newest first):
        [open, close, high, low, change_html, pct_html, greg_date, shamsi_date]
    Values are in RIALS -> divide by 10 for Toman.

Verified symbol ids (Oct 2026):
    sekee    = سکه امامی (Emami coin)
    sekeb    = سکه بهار آزاد
    geram18  = طلا ۱۸ (18k gold per gram)
    mesghal  = مثقال (Mesghal, 4.608g of 17k gold)

Melt value (ارزش ذوب)
----------------------
    gold18_melt = ounce_usd * usd_toman * (0.75 / 31.1035)      # 18k = 75% purity
    mesghal_melt = ounce_usd * usd_toman * (0.705 / 31.1035) * 4.608  # 17k mesghal
    coin_melt    = gold18_melt * 8.133                            # Emami = 8.133g of 18k

Premium (حاشیه بازار)
---------------------
    premium % = (domestic_price / melt_value - 1) * 100
    A shrinking premium = the market is pricing less local stress -> bearish for
    the domestic instrument (less panic bid), a growing premium = more stress.
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iran_gold.json")

SYMBOLS = {
    "coin_emami": "sekee",     # سکه امامی
    "coin_bahar": "sekeb",     # سکه بهار آزاد
    "gold18": "geram18",       # طلا ۱۸ هر گرم
    "mesghal": "mesghal",      # مثقال
}

GRAM_18K_PER_OUNCE = 0.75 / 31.1035          # 18k gold per troy ounce in grams
GRAM_17K_PER_OUNCE = 0.705 / 31.1035
MESGHAL_GRAMS = 4.608                        # 4.608g of 17k
EMAMI_GRAMS = 8.133                          # Emami coin = 8.133g of 18k


def _get(url, timeout=30, tries=2):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            last = e
            if i < tries - 1:
                time.sleep(2)
    raise last


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("٬", "").strip())
    except (TypeError, ValueError):
        return None


def fetch_series(symbol, length=180):
    """Return a newest-first list of closes (Toman) for a TGJU symbol."""
    url = (f"https://api.tgju.org/v1/market/indicator/summary-table-data/{symbol}"
           f"?lang=fa&order_dir=desc&draw=1&start=0&length={length}")
    raw = _get(url)
    d = json.loads(raw)
    rows = d.get("data") or []
    out = []
    for r in rows:
        if not isinstance(r, list) or len(r) < 7:
            continue
        close = _num(r[1])          # index 1 = close
        date = r[6] if len(r) > 6 else None
        if close is None:
            continue
        out.append({"date": date, "close": close / 10.0})   # rial -> toman
    return out


def stats(series):
    """Trend statistics from a newest-first close list."""
    if not series or len(series) < 6:
        return None
    closes = [s["close"] for s in series]
    last = closes[0]
    def chg(n):
        return (last / closes[n] - 1) * 100 if len(closes) > n else None
    ma20 = sum(closes[:20]) / min(20, len(closes))
    ma50 = sum(closes[:50]) / min(50, len(closes))
    return {
        "last": round(last, 1),
        "last_date": series[0].get("date"),
        "chg_5d_pct": round(chg(5), 3) if chg(5) is not None else None,
        "chg_20d_pct": round(chg(20), 3) if chg(20) is not None else None,
        "chg_60d_pct": round(chg(60), 3) if chg(60) is not None else None,
        "ma20": round(ma20, 1),
        "ma50": round(ma50, 1),
        "above_ma20": last > ma20,
        "above_ma50": last > ma50,
        "n": len(closes),
    }


def build():
    out = {"fetched_at": datetime.now(IRAN_TZ).isoformat(), "instruments": {}, "errors": []}

    for key, sym in SYMBOLS.items():
        try:
            s = fetch_series(sym)
            if s:
                out["instruments"][key] = {"symbol": sym, **stats(s)}
                st = out["instruments"][key]
                print(f"  OK    {key:<12} {sym:<9} last={st['last']:>14,.0f} "
                      f"20d={st['chg_20d_pct']}% >ma20={st['above_ma20']} >ma50={st['above_ma50']}")
            else:
                out["errors"].append(f"{sym}: empty")
                print(f"  EMPTY {key:<12} {sym}")
        except Exception as e:
            out["errors"].append(f"{sym}: {type(e).__name__}: {e}")
            print(f"  FAIL  {key:<12} {sym}  {type(e).__name__}")

    return out


def main():
    out = build()
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nwrote {OUT}")
    if out["errors"]:
        print("errors:", out["errors"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
