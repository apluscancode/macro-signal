/* Unified signal board — extra macro cards.
   Each card shows one verdict word + the raw number, no charts.
   Sources: alternative.me (F&G), coingecko.global (dominance), farside (ETF flow)
*/
(function () {
  'use strict';

  var CARDS = [
    {
      id: 'fng-card',
      verdictId: 'fng-verdict',
      metaId: 'fng-meta',
      confId: 'fng-conf',
      read: function (d) {
        var f = d.fear_greed;
        if (!f || f.value === undefined || f.value === null) return null;
        var v = Number(f.value);
        var verdict, state, note;
        if (v <= 25)      { verdict = 'BUY';    state = 'buy';  note = 'ترس شدید — فرصت خرید'; }
        else if (v <= 45) { verdict = 'BUY';    state = 'buy';  note = 'ترس — تدریجی خرید'; }
        else if (v <= 55) { verdict = 'HOLD';   state = 'hold'; note = 'خنثی — صبر کن'; }
        else if (v <= 75) { verdict = 'HOLD';   state = 'hold'; note = 'طمع ملایم — احتیاط'; }
        else              { verdict = 'SELL';   state = 'sell'; note = 'طمع شدید — خطر اصلاح'; }
        return {
          verdict: verdict, state: state, value: v,
          conf: (f.classification || ''),
          meta: f.classification + ' — ' + note
        };
      }
    },
    {
      id: 'dom-card',
      verdictId: 'dom-verdict',
      metaId: 'dom-meta',
      confId: 'dom-conf',
      read: function (d) {
        var x = d.btc_dominance;
        if (!x || x.btc_dominance_pct === undefined) return null;
        var v = Number(x.btc_dominance_pct);
        var verdict, state, note;
        if (v < 50)      { verdict = 'BUY';  state = 'buy';  note = 'دومینیانس بیت‌کوین ضعیف — آلت‌کوین‌ها قوی‌تر'; }
        else if (v <= 60) { verdict = 'HOLD'; state = 'hold'; note = 'دومینیانس متعادل'; }
        else              { verdict = 'SELL'; state = 'sell'; note = 'دومینیانس بالا — پول روی بیت‌کوین متمرکز'; }
        return {
          verdict: verdict, state: state, value: v.toFixed(2) + '%',
          conf: '',
          meta: note
        };
      }
    },
    {
      id: 'etf-card',
      verdictId: 'etf-verdict',
      metaId: 'etf-meta',
      confId: 'etf-conf',
      read: function (d) {
        var e = d.etf_flow;
        if (!e || !e.daily_flows || !e.daily_flows.length) return null;
        var last = e.daily_flows[e.daily_flows.length - 1];
        var v = Number(last.net_flow_m);
        // average of the last 5 sessions for a smoother read
        var recent = e.daily_flows.slice(-5);
        var sum = 0, n = 0;
        recent.forEach(function (x) { sum += Number(x.net_flow_m); n++; });
        var avg5 = n ? sum / n : 0;
        var verdict, state, note;
        if (avg5 > 100)      { verdict = 'BUY';  state = 'buy';  note = 'ورود پول قوی به ETF — تقاضای بیت‌کوین بالا'; }
        else if (avg5 > -100) { verdict = 'HOLD'; state = 'hold'; note = 'جریان پول ETF خنثی'; }
        else                 { verdict = 'SELL'; state = 'sell'; note = 'خروج پول از ETF — ضعف تقاضا'; }
        var sign = v > 0 ? '+' : '';
        return {
          verdict: verdict, state: state,
          value: sign + v.toFixed(0) + 'M',
          conf: '5d avg ' + (avg5 > 0 ? '+' : '') + avg5.toFixed(0) + 'M',
          meta: last.date + ' — ' + note
        };
      }
    }
  ];

  function paint(card, r) {
    var el = document.getElementById(card.id);
    if (!el) return;
    var v = document.getElementById(card.verdictId);
    var c = document.getElementById(card.confId);
    var m = document.getElementById(card.metaId);
    el.setAttribute('data-state', r.state);
    v.textContent = r.verdict;
    c.textContent = r.conf || '';
    m.textContent = r.meta;
  }

  function loadMacroExtra() {
    fetch('data/macro_extra.json?t=' + Date.now(), { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (d) {
        CARDS.forEach(function (card) {
          var r = card.read(d);
          if (!r) {
            var el = document.getElementById(card.id);
            if (el) { el.setAttribute('data-state', 'error'); document.getElementById(card.verdictId).textContent = 'OFFLINE'; }
            return;
          }
          paint(card, r);
          // the big number lives in the conf slot for these cards
          var c = document.getElementById(card.confId);
          if (c && r.value) c.textContent = r.value + (r.conf ? ' · ' + r.conf : '');
        });
      })
      .catch(function () {
        CARDS.forEach(function (card) {
          var el = document.getElementById(card.id);
          if (el) { el.setAttribute('data-state', 'error'); document.getElementById(card.verdictId).textContent = 'OFFLINE'; }
        });
      });
  }

  loadMacroExtra();
  setInterval(loadMacroExtra, 5 * 60 * 1000);
})();