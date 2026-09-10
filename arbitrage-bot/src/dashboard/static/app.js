(() => {
  const $ = (id) => document.getElementById(id);
  let lastBtc = null;
  let ws;

  function fmt(n, d = 2) {
    if (n == null || Number.isNaN(n)) return "—";
    return Number(n).toLocaleString(undefined, {
      minimumFractionDigits: d,
      maximumFractionDigits: d,
    });
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    $("connPill").textContent = "connecting";
    $("connPill").className = "pill";

    ws.onopen = () => {
      $("connPill").textContent = "live";
      $("connPill").className = "pill live";
      // keepalive
      setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 15000);
    };

    ws.onclose = () => {
      $("connPill").textContent = "reconnecting";
      $("connPill").className = "pill down";
      setTimeout(connect, 1500);
    };

    ws.onerror = () => ws.close();
    ws.onmessage = (ev) => {
      try {
        render(JSON.parse(ev.data));
      } catch (_) {}
    };
  }

  function render(data) {
    $("metaLine").textContent =
      `${data.markets || 0}/${data.configured_symbols || 0} books · ` +
      `${data.triangles || 0} triangles · ` +
      `${data.ws_messages || 0} ticks · ` +
      `scan #${data.scans || 0} · ` +
      `up ${fmt(data.uptime_sec, 0)}s`;

    $("mode").textContent = data.paper_trading ? "PAPER" : "LIVE";
    $("modeSub").textContent = data.paper_trading
      ? "Simulated fills at net edge after fees"
      : "Live trading path requires signed orders";
    $("disclaimer").textContent = data.disclaimer || "";

    const btc = data.btc;
    if (btc) {
      const el = $("btcPrice");
      el.textContent = `$${fmt(btc.mid, 2)}`;
      if (lastBtc != null) {
        el.className = "btc-price " + (btc.mid >= lastBtc ? "up" : "down");
      }
      lastBtc = btc.mid;
      $("btcSub").textContent =
        `bid ${fmt(btc.bid, 2)} · ask ${fmt(btc.ask, 2)} · spread ${fmt(btc.spread_bps, 2)} bps`;
    }

    const p = data.portfolio || {};
    $("equity").textContent = `$${fmt(p.equity_usd, 2)}`;
    const pnlSign = (p.realized_pnl_usd || 0) >= 0 ? "+" : "";
    $("pnl").textContent =
      `PnL ${pnlSign}$${fmt(p.realized_pnl_usd, 4)} · ${pnlSign}${fmt(p.return_pct, 3)}% · ${p.trade_count || 0} fills`;
    $("tradeCount").textContent = String(p.trade_count || 0);

    const opps = data.opportunities || [];
    $("oppCount").textContent = String(opps.length);
    const oppList = $("oppList");
    if (!opps.length) {
      oppList.innerHTML =
        `<p class="empty">No net-positive opportunities right now (after ~${10} bps/leg fees). Watching…</p>`;
    } else {
      oppList.innerHTML = opps
        .slice(0, 12)
        .map((o) => {
          const tradeable = o.net_edge_bps >= 8;
          const weak = !tradeable;
          const edgeClass = tradeable ? "edge" : "";
          const tag = tradeable ? "TRADEABLE" : "WATCH";
          return `<article class="opp ${weak ? "weak" : ""}">
            <div class="title">${tag} · ${o.kind} · <span class="${edgeClass}">${fmt(o.net_edge_bps, 2)} bps net</span> · ${fmt(o.gross_edge_bps, 2)} gross</div>
            <div class="sub">${(o.path || []).join(" → ")} · $${fmt(o.notional_usd, 2)} · ${o.detail || ""}</div>
          </article>`;
        })
        .join("");
    }

    const fills = p.recent_trades || [];
    const fillList = $("fillList");
    if (!fills.length) {
      fillList.innerHTML =
        `<p class="empty">No paper fills yet. Edges after fees are uncommon on a single venue.</p>`;
    } else {
      fillList.innerHTML = fills
        .slice(0, 15)
        .map(
          (f) => `<article class="fill">
            <div class="title">#${f.id} · +$${fmt(f.expected_pnl_usd, 4)} · ${fmt(f.net_edge_bps, 2)} bps</div>
            <div class="sub">${(f.path || []).join(" → ")} · $${fmt(f.notional_usd, 2)} · ${f.detail || ""}</div>
          </article>`
        )
        .join("");
    }

    const markets = data.markets_snapshot || {};
    const rows = Object.values(markets);
    $("marketCount").textContent = `${rows.length} markets`;
    const body = $("marketBody");
    body.innerHTML = rows
      .sort((a, b) => a.symbol.localeCompare(b.symbol))
      .map((m) => {
        const decimals = m.mid >= 100 ? 2 : m.mid >= 1 ? 4 : 6;
        return `<tr>
          <td>${m.symbol}</td>
          <td class="num">${fmt(m.bid, decimals)}</td>
          <td class="num">${fmt(m.ask, decimals)}</td>
          <td class="num">${fmt(m.mid, decimals)}</td>
          <td class="num">${fmt(m.spread_bps, 2)}</td>
        </tr>`;
      })
      .join("");
  }

  connect();
})();
