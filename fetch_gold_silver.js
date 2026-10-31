/* Gold/Silver ratio fetcher.
   ratio = XAUUSD / XAGUSD
   > 70  -> SELL GOLD / BUY SILVER
   < 55  -> BUY GOLD / SELL SILVER
   else  -> HOLD
   Usage: node fetch_gold_silver.js     -> writes data/gold_silver.json
*/
const TV = require('@mathieuc/tradingview');
const fs = require('fs');
const path = require('path');

const OUT = path.join(__dirname, 'data', 'gold_silver.json');

const PAIRS = [
  { key: 'gold',   symbol: 'OANDA:XAUUSD', label: 'اونس طلا' },
  { key: 'silver', symbol: 'OANDA:XAGUSD', label: 'اونس نقره' },
];

async function quote(symbol) {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const client = new TV.Client();
      const chart = new client.Session.Chart();
      chart.setMarket(symbol, { timeframe: 'D', range: 30 });
      await new Promise(r => setTimeout(r, 2200));
      const periods = chart.periods || [];
      if (periods.length) {
        const closes = periods.map(p => p.close).filter(v => typeof v === 'number');
        if (closes.length) {
          return {
            last: closes[0],
            chg_5d_pct: closes.length > 5 ? +(((closes[0] / closes[5] - 1) * 100).toFixed(3)) : null,
            ma20: +((closes.slice(0, 20).reduce((a, b) => a + b, 0) / Math.min(20, closes.length)).toFixed(4)),
            n: closes.length,
          };
        }
      }
    } catch (e) { /* retry */ }
  }
  return null;
}

(async () => {
  const out = { fetched_at: new Date().toISOString(), source: 'tradingview' };
  for (const p of PAIRS) {
    const q = await quote(p.symbol);
    if (!q) { console.error(`FAIL ${p.key}`); process.exit(1); }
    out[p.key] = { ...q, symbol: p.symbol, label: p.label };
    console.log(`  OK    ${p.key.padEnd(7)} ${p.symbol.padEnd(16)} last=${q.last}`);
  }

  const ratio = out.gold.last / out.silver.last;
  out.ratio = +ratio.toFixed(4);

  if (ratio > 70) {
    out.signal = 'SELL GOLD / BUY SILVER';
    out.signal_fa = 'فروش طلا / خرید نقره';
    out.zone = 'overvalued';
    out.advice = 'نسبت طلا به نقره بالای ۷۰ است — طلا بیش‌ازحد گران شده. تبدیل طلا به نقره';
  } else if (ratio < 55) {
    out.signal = 'BUY GOLD / SELL SILVER';
    out.signal_fa = 'خرید طلا / فروش نقره';
    out.zone = 'undervalued';
    out.advice = 'نسبت طلا به نقره زیر ۵۵ است — نقره بیش‌ازحد گران شده. تبدیل نقره به طلا';
  } else {
    out.signal = 'HOLD';
    out.signal_fa = 'نگهداری';
    out.zone = 'neutral';
    out.advice = 'نسبت طلا به نقره بین ۵۵ تا ۷۰ است — زمان تبدیل نیست';
  }

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(out, null, 2));
  console.log(`\nratio = ${out.ratio}  ->  ${out.signal}`);
  console.log(`wrote ${OUT}`);
  process.exit(0);
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
