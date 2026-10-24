/* Market history fetcher for the macro signal engine.
   TradingView is the primary source: no API key, no rate limit, full history.
   Usage:  node fetch_market.js            -> writes market_history.json
           node fetch_market.js --probe    -> prints and exits (no write)   */
const TV = require('@mathieuc/tradingview');
const fs = require('fs');
const path = require('path');

const OUT = path.join(__dirname, 'market_history.json');

const SYMBOLS = [
  { key: 'gold',   symbol: 'OANDA:XAUUSD', label: 'Gold spot (OANDA)' },
  { key: 'dxy',    symbol: 'TVC:DXY',      label: 'Dollar index (TVC)' },
  { key: 'oil',    symbol: 'TVC:USOIL',    label: 'WTI crude (TVC)' },
  { key: 'brent',  symbol: 'TVC:UKOIL',    label: 'Brent crude (TVC)' },
  { key: 'vix',    symbol: 'CBOE:VIX',     label: 'VIX (CBOE)' },
  { key: 'spx',    symbol: 'SP:SPX',       label: 'S&P 500 (SP)' },
  { key: 'btc',    symbol: 'BINANCE:BTCUSDT', label: 'Bitcoin (Binance)' },
];

const RANGE = 120;   // ~6 months of daily bars

function stats(periods) {
  // TradingView returns NEWEST FIRST
  const closes = periods.map(p => p.close).filter(v => typeof v === 'number');
  if (closes.length < 25) return null;
  const last = closes[0];
  const chg = n => (closes.length > n ? ((last / closes[n] - 1) * 100) : null);
  const avg = n => {
    const w = closes.slice(0, n);
    return w.length ? w.reduce((a, b) => a + b, 0) / w.length : null;
  };
  const ma20 = avg(20), ma50 = avg(50);
  return {
    last: +last.toFixed(4),
    chg_5d_pct: chg(5) === null ? null : +chg(5).toFixed(3),
    chg_20d_pct: chg(20) === null ? null : +chg(20).toFixed(3),
    chg_60d_pct: chg(60) === null ? null : +chg(60).toFixed(3),
    ma20: ma20 === null ? null : +ma20.toFixed(4),
    ma50: ma50 === null ? null : +ma50.toFixed(4),
    above_ma20: ma20 === null ? null : last > ma20,
    above_ma50: ma50 === null ? null : last > ma50,
    n: closes.length,
  };
}

(async () => {
  const probe = process.argv.includes('--probe');
  const out = { source: 'tradingview', fetched_at: new Date().toISOString(), series: {} };

  for (const s of SYMBOLS) {
    let ok = false;
    let st = null;
    // one retry — TradingView occasionally returns an empty first frame
    for (let attempt = 0; attempt < 2 && !ok; attempt++) {
      try {
        const client = new TV.Client();
        const chart = new client.Session.Chart();
        chart.setMarket(s.symbol, { timeframe: 'D', range: RANGE });
        await new Promise(r => setTimeout(r, 2200));
        const periods = chart.periods || [];
        if (periods.length) {
          st = stats(periods);
          if (st) ok = true;
        }
      } catch (e) { /* try again */ }
    }
    if (ok) {
      out.series[s.key] = { ...st, symbol: s.symbol, label: s.label };
      console.log(`  OK    ${s.key.padEnd(6)} ${s.symbol.padEnd(20)} last=${st.last} 20d=${st.chg_20d_pct}% >ma20=${st.above_ma20} >ma50=${st.above_ma50}`);
    } else {
      console.log(`  FAIL  ${s.key.padEnd(6)} ${s.symbol}`);
    }
  }

  if (probe) { console.log('\n(probe mode — nothing written)'); process.exit(0); }

  fs.writeFileSync(OUT, JSON.stringify(out, null, 2));
  console.log(`\nwrote ${OUT} (${Object.keys(out.series).length} series)`);
  process.exit(0);
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
