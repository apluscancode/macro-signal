#!/usr/bin/env python3
"""
Fetch extra macro indicators for the unified signal board:
- Fear & Greed Index (Alternative.me)
- BTC Dominance (CoinGecko global)
- ETF Net Flow (Farside via r.jina.ai)

Writes: data/macro_extra.json
"""
import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (compatible; MacroSignal/1.0)"}
TIMEOUT = 25
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))
OUT = Path(__file__).parent / "data" / "macro_extra.json"


def _get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        return data.decode("utf-8", "ignore")


def fetch_fng() -> dict | None:
    """Fear & Greed Index from Alternative.me"""
    try:
        txt = _get("https://api.alternative.me/fng/?limit=1")
        d = json.loads(txt)
        if d.get("data"):
            row = d["data"][0]
            val = int(row["value"])
            classification = row["value_classification"]
            return {
                "value": val,
                "classification": classification,
                "source": "alternative.me",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        return {"error": str(e), "source": "alternative.me"}
    return None


def fetch_dominance() -> dict | None:
    """BTC Dominance from CoinGecko global"""
    try:
        txt = _get("https://api.coingecko.com/api/v3/global")
        d = json.loads(txt)
        data = d.get("data", {})
        btc_dom = data.get("market_cap_percentage", {}).get("btc")
        if btc_dom is not None:
            return {
                "btc_dominance_pct": round(float(btc_dom), 2),
                "total_market_cap_usd": data.get("total_market_cap", {}).get("usd"),
                "source": "coingecko.global",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        return {"error": str(e), "source": "coingecko.global"}
    return None


def fetch_etf_flow() -> dict | None:
    """ETF Net Flow from Farside (via r.jina.ai)"""
    try:
        txt = _get("https://r.jina.ai/https://farside.co.uk/btc/")
        # Parse the markdown table - look for the "Total" row and daily rows
        lines = txt.split("\n")
        total_flow = None
        daily_flows = []
        in_table = False

        for line in lines:
            line = line.strip()
            if not line or not line.startswith("|"):
                continue
            in_table = True
            parts = [p.strip() for p in line.split("|")[1:-1]]  # remove empty first/last
            if not parts:
                continue

            # Header row detection
            if parts and "IBIT" in parts[0]:
                continue  # skip header
            if parts and "Fee" in parts[0]:
                continue  # skip fee row

            # Total row
            if parts and parts[0].lower() == "total":
                try:
                    total_flow = float(parts[-1].replace(",", "").replace("(", "-").replace(")", ""))
                except:
                    pass
                continue

            # Daily flow row (date | values...)
            if parts and re.match(r"\d{1,2}\s+\w+\s+\d{4}", parts[0]):
                raw = parts[-1].replace(",", "").strip()
                # Farside prints "-" for sessions with no data yet (today, before
                # the close). Skip those instead of recording a fake 0.0 flow.
                if raw in ("-", "", "–", "—"):
                    continue
                # The session row can show a 0.0 total while every individual
                # fund is still "-". Treat that as "no data yet" as well.
                funds = [p.replace(",", "").strip() for p in parts[1:-1]]
                if funds and all(f in ("-", "", "–", "—") for f in funds):
                    continue
                try:
                    daily_val = float(raw.replace("(", "-").replace(")", ""))
                    daily_flows.append({"date": parts[0], "net_flow_m": daily_val})
                except:
                    pass

        if total_flow is not None:
            return {
                "total_net_flow_m": total_flow,
                "daily_flows": daily_flows[-14:],  # last 14 days
                "latest_daily": daily_flows[-1] if daily_flows else None,
                "source": "farside.co.uk via jina.ai",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        return {"error": str(e), "source": "farside"}
    return None


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)

    fng = fetch_fng()
    dom = fetch_dominance()
    etf = fetch_etf_flow()

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "fetched_at_iran": datetime.now(IRAN_TZ).strftime("%Y-%m-%d %H:%M Iran"),
        "fear_greed": fng,
        "btc_dominance": dom,
        "etf_flow": etf,
    }

    with OUT.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("Written:", OUT)
    print(json.dumps(result, ensure_ascii=False, indent=1)[:1500])


if __name__ == "__main__":
    main()