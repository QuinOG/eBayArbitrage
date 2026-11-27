document.addEventListener("DOMContentLoaded", async function () {
  const $ = id => document.getElementById(id);
  const { esc, money, safeUrl } = window.Parts;
  const loadingScreen = $("loading");
  const hero = $("hero");
  const bench = $("bench");
  const overview = $("overview");
  const chart = $("chart");
  const tip = $("chart-tip");
  const container = $("deals-container");
  const dealsHead = $("deals-head");
  const dealsCount = $("deals-count");
  const summary = $("summary");
  const errorsBox = $("errors");
  const searchFilters = $("search-filters");
  const hideLow = $("hide_low");
  const minProfitSelect = $("min_profit");
  const sortSelect = $("sort_by");

  let listings = [];
  let configMin = 20;
  let pool = [];          // listings in the chart: checked searches, after "hide low confidence"
  let scannedAt = new Date();
  let firstRender = true;

  // A cost line: "-$60.00", or "$0.00" when there is nothing to subtract.
  const cost = n => (n ? money(-n) : money(0));
  const allIn = d => d.price + d.shipping + d.tax;

  // The profit cutoff picked in the dropdown. "all" shows losses too.
  function minimumProfit() {
    return minProfitSelect.value === "all" ? -Infinity : parseFloat(minProfitSelect.value);
  }

  // What counts as a deal. With "all" selected, the config minimum still decides.
  function dealMin() {
    return minProfitSelect.value === "all" ? configMin : parseFloat(minProfitSelect.value);
  }

  const isDeal = d => d.profit >= dealMin();

  // ------------------------------------------------------------------
  // Receipts
  // ------------------------------------------------------------------

  // Spread bar: the parts value split into price, shipping, tax and what you keep.
  // On a loss the bar is the cost, with a red tick where the parts value runs out.
  function spreadBar(d) {
    const segs = [["price", d.price], ["shipping", d.shipping], ["tax", d.tax], ["profit", Math.max(0, d.profit)]]
      .filter(s => s[1] > 0)
      .map(([k, v]) => `<span class="seg seg-${k}" style="flex-grow:${v}"></span>`)
      .join("");
    const spent = allIn(d);
    const mark = d.profit < 0 && spent > 0
      ? `<span class="spread-mark" style="left:${(d.parts_value / spent) * 100}%"></span>`
      : "";
    return `<div class="spread" aria-hidden="true">${segs}${mark}</div>`;
  }

  function line(label, value, cls = "", sw = "") {
    return `
      <li class="${cls}">
        <span class="l-name">${sw ? `<i class="sw seg-${sw}"></i>` : ""}${label}</span>
        <span class="l-dots"></span>
        <span class="l-val">${value}</span>
      </li>`;
  }

  function partLine(p) {
    let source = p.kind;
    if (p.kind === "fallback") source = `fallback: ${p.priced_as}`;
    const high = p.confidence === "high";
    const data = p.kind === "no data" ? "no sold data" : `${p.sales} sold · ${p.confidence} · ${source}`;
    return `
      <li class="part ${high ? "" : "low-row"}">
        <span class="l-name">${esc(p.model)}<small>${esc(p.name)} · ${esc(data)}</small></span>
        <span class="l-dots"></span>
        <span class="l-val">${money(p.value)}</span>
      </li>`;
  }

  // The verdict in the corner: an ink stamp for a buy, a check or a loss, plain text otherwise.
  function verdict(d) {
    if (d.profit < 0) return `<div class="stamp pass"><b>Pass</b><span>${money(d.profit)}</span></div>`;
    if (!isDeal(d)) return `<div class="r-verdict">+${money(d.profit)}<span>under $${dealMin()}</span></div>`;
    const low = d.confidence === "low";
    return `<div class="stamp ${low ? "check" : "buy"}"><b>${low ? "Check" : "Buy"}</b><span>+${money(d.profit)}</span></div>`;
  }

  function createCard(d) {
    const wrap = document.createElement("div");
    wrap.className = "receipt-wrap";
    const low = d.confidence === "low";
    const cls = ["receipt", isDeal(d) ? "deal-card" : "no-deal-card", low ? "low-card" : "", d.profit < 0 ? "loss" : ""].join(" ");
    const parts = d.parts.length
      ? d.parts.map(partLine).join("")
      : `<li class="part"><span class="l-name unknown">No parts identified</span></li>`;
    const flags = d.flags.length
      ? `<ul class="flags">${d.flags.map(f => `<li>${esc(f)}</li>`).join("")}</ul>`
      : "";
    const meta = [d.search, d.condition, d.post_date].filter(Boolean).map(esc).join(" · ");
    const margin = d.parts_value > 0 ? `${Math.round((d.profit / d.parts_value) * 100)}%` : "none";

    wrap.innerHTML = `
      <article class="${cls}" id="deal-${d._key}" data-key="${d._key}">
        <div class="r-head">
          ${verdict(d)}
          <p class="r-meta">${meta}</p>
          <h2><a href="${safeUrl(d.listing_url)}" target="_blank" rel="noopener">${esc(d.title)}</a></h2>
        </div>
        ${spreadBar(d)}
        <ul class="lines">
          ${parts}
          ${line("Parts value", money(d.parts_value), "sub")}
          ${line("Price", cost(d.price), "", "price")}
          ${line("Shipping", cost(d.shipping), "", "shipping")}
          ${line("Sales tax", cost(d.tax), "", "tax")}
          ${line("Profit", money(d.profit), "total", "profit")}
          ${line("Margin", margin, "margin")}
        </ul>
        ${flags}
      </article>`;
    return wrap;
  }

  // ------------------------------------------------------------------
  // Hero: the scan in one sentence, and the best flip laid out on the bench
  // ------------------------------------------------------------------
  function drawHero() {
    const dm = dealMin();
    const deals = pool.filter(isDeal).sort((a, b) => b.profit - a.profit);
    const n = deals.length;
    const profit = deals.reduce((s, d) => s + d.profit, 0);
    const spend = deals.reduce((s, d) => s + allIn(d), 0);
    const best = deals[0];

    const time = scannedAt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).toLowerCase();
    const checked = [...searchFilters.querySelectorAll("input:checked")].map(cb => cb.value);
    summary.textContent = `Scanned at ${time} · ${checked.join(", ") || "no searches selected"}`;

    $("headline").innerHTML =
      `<span class="n">${n}</span> of <span class="n">${pool.length}</span> listings ${n === 1 ? "clears" : "clear"} <span class="n">$${dm}</span>`;
    $("hero-sub").innerHTML = n
      ? `Buy ${n === 1 ? "it" : `all ${n}`} for <span class="n">${money(spend)}</span> with shipping and tax, sell the parts, and keep <span class="n accent">${money(profit)}</span>`
      : `Nothing clears your minimum with these filters. Lower the minimum or include more searches.`;

    if (!best) {
      bench.innerHTML = `<p class="bench-empty">The best flip shows up here once a listing clears $${dm}</p>`;
      return;
    }
    const drawn = best.parts.filter(p => p.model);
    bench.innerHTML = `
      <figcaption class="bench-caption">
        <span>Best flip</span>
        <a href="#deal-${best._key}" data-key="${best._key}">${esc(best.title)}</a>
      </figcaption>
      <div class="bench-items">${drawn.length ? window.Parts.items(drawn) : `<p class="bench-empty">No parts identified in the title</p>`}</div>
      <p class="bench-sum">
        <span>${money(best.parts_value)} parts</span>
        <span class="op">−</span>
        <span>${money(allIn(best))} in</span>
        <span class="op">=</span>
        <strong>${money(best.profit)}</strong>
      </p>`;
  }

  bench.addEventListener("click", e => {
    const a = e.target.closest("a[data-key]");
    if (a) { e.preventDefault(); jumpTo(a.dataset.key); }
  });

  // ------------------------------------------------------------------
  // Chart: what a listing costs (x) against what its parts sell for (y), on graph paper
  // ------------------------------------------------------------------
  function niceStep(raw) {
    const p = 10 ** Math.floor(Math.log10(raw));
    const n = raw / p;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
  }

  function drawChart(shownKeys) {
    const W = chart.clientWidth || 640;
    const H = chart.clientHeight || 300;
    const m = { l: 56, r: 12, t: 28, b: 40 };
    const top = Math.max(50, ...pool.map(d => Math.max(allIn(d), d.parts_value)));
    const step = niceStep(top / 4);
    const D = Math.ceil((top * 1.08) / step) * step;
    const x = v => m.l + (v / D) * (W - m.l - m.r);
    const y = v => H - m.b - (v / D) * (H - m.t - m.b);
    const dm = dealMin();

    let grid = "";
    for (let v = 0; v <= D + 0.001; v += step / 4) {
      const major = Math.abs(v / step - Math.round(v / step)) < 0.001;
      grid += `<line class="${major ? "major" : "minor"}" x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/>`;
      grid += `<line class="${major ? "major" : "minor"}" y1="${m.t}" y2="${H - m.b}" x1="${x(v)}" x2="${x(v)}"/>`;
      if (major) {
        grid += `<text class="tick" x="${m.l - 8}" y="${y(v) + 4}" text-anchor="end">$${v}</text>`;
        grid += `<text class="tick" x="${x(v)}" y="${H - m.b + 18}" text-anchor="middle">$${v}</text>`;
      }
    }

    const angle = (Math.atan2(y(D) - y(0), x(D) - x(0)) * 180) / Math.PI;
    const lv = D * 0.8;
    const mv = Math.max(0, Math.min(D * 0.55, D - dm - step * 0.2));
    const zone = dm < D
      ? `<polygon class="zone" points="${x(0)},${y(Math.max(0, dm))} ${x(D - Math.max(0, dm))},${y(D)} ${x(0)},${y(D)}"/>`
      : "";
    const minLine = dm < D
      ? `<line class="min-line" x1="${x(0)}" y1="${y(dm)}" x2="${x(D - dm)}" y2="${y(D)}"/>
         <text class="line-label min-label" transform="translate(${x(mv)},${y(mv + dm) - 8}) rotate(${angle})">+$${dm} profit</text>`
      : "";

    // Deals last so they sit on top.
    const pts = pool.slice().sort((a, b) => isDeal(a) - isDeal(b)).map(d => {
      const cls = ["pt", isDeal(d) ? "deal" : "", d.confidence === "low" ? "low" : "", shownKeys.has(d._key) ? "" : "filtered"].join(" ");
      return `<g class="${cls}" data-key="${d._key}" transform="translate(${x(allIn(d))},${y(d.parts_value)})" tabindex="0" role="button"
                aria-label="${esc(d.title)}, profit ${money(d.profit)}">
                <circle class="hit" r="12"/><circle class="mark" r="5"/></g>`;
    }).join("");

    chart.innerHTML = `
      <svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">
        <g class="grid">${grid}</g>
        ${zone}
        <line class="even" x1="${x(0)}" y1="${y(0)}" x2="${x(D)}" y2="${y(D)}"/>
        <text class="line-label" transform="translate(${x(lv)},${y(lv) + 16}) rotate(${angle})">break-even</text>
        ${minLine}
        <text class="axis-label" x="${W - m.r}" y="${H - 4}" text-anchor="end">Cost with shipping and tax</text>
        <text class="axis-label" x="${m.l - 8}" y="12" text-anchor="end">Parts value</text>
        <g class="pts">${pts}</g>
      </svg>`;
  }

  function byKey(key) {
    return listings.find(d => String(d._key) === String(key));
  }

  function showTip(g) {
    const d = byKey(g.dataset.key);
    if (!d) return;
    const hidden = g.classList.contains("filtered");
    tip.innerHTML = `
      <div class="tip-title">${esc(d.title)}</div>
      <div class="tip-figures">${money(d.profit)} profit · ${money(allIn(d))} in · ${money(d.parts_value)} parts</div>
      ${hidden ? `<div class="tip-note">Below the minimum, not in the list</div>` : ""}`;
    tip.hidden = false;
    const wrap = chart.getBoundingClientRect();
    const r = g.getBoundingClientRect();
    const cx = r.left + r.width / 2 - wrap.left;
    const cy = r.top - wrap.top;
    const left = Math.min(Math.max(0, cx - tip.offsetWidth / 2), wrap.width - tip.offsetWidth);
    tip.style.left = left + "px";
    tip.style.top = Math.max(0, cy - tip.offsetHeight - 8) + "px";
    linkCard(d._key, true);
  }

  function hideTip(g) {
    tip.hidden = true;
    if (g) linkCard(g.dataset.key, false);
  }

  function linkCard(key, on) {
    const card = $("deal-" + key);
    if (card) card.classList.toggle("linked", on);
  }

  function jumpTo(key) {
    const card = $("deal-" + key);
    if (!card) return;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.classList.remove("flash");
    void card.offsetWidth; // restart the animation
    card.classList.add("flash");
  }

  chart.addEventListener("mouseover", e => { const g = e.target.closest(".pt"); if (g) showTip(g); });
  chart.addEventListener("mouseout", e => { const g = e.target.closest(".pt"); if (g && !g.contains(e.relatedTarget)) hideTip(g); });
  chart.addEventListener("focusin", e => { const g = e.target.closest(".pt"); if (g) showTip(g); });
  chart.addEventListener("focusout", e => { const g = e.target.closest(".pt"); if (g) hideTip(g); });
  chart.addEventListener("click", e => { const g = e.target.closest(".pt"); if (g) jumpTo(g.dataset.key); });
  chart.addEventListener("keydown", e => {
    const g = e.target.closest(".pt");
    if (g && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); jumpTo(g.dataset.key); }
  });

  // Hovering a receipt lifts its dot in the chart.
  container.addEventListener("mouseover", e => {
    const card = e.target.closest(".receipt");
    chart.querySelectorAll(".pt.on").forEach(p => p.classList.remove("on"));
    if (card) chart.querySelector(`.pt[data-key="${card.dataset.key}"]`)?.classList.add("on");
  });
  container.addEventListener("mouseleave", () => chart.querySelectorAll(".pt.on").forEach(p => p.classList.remove("on")));

  // ------------------------------------------------------------------
  function render() {
    const min = minimumProfit();
    const checked = Array.from(searchFilters.querySelectorAll("input:checked")).map(cb => cb.value);
    pool = listings.filter(d => checked.includes(d.search) && !(hideLow.checked && d.confidence === "low"));
    let shown = pool.filter(d => d.profit >= min);

    const sort = sortSelect.value;
    if (sort === "profit") shown.sort((a, b) => b.profit - a.profit);
    if (sort === "newest") shown.sort((a, b) => new Date(b.created) - new Date(a.created));
    if (sort === "price_asc") shown.sort((a, b) => a.price - b.price);

    $("legend-min").textContent = "$" + dealMin();
    drawHero();
    drawChart(new Set(shown.map(d => d._key)));

    container.innerHTML = "";
    shown.forEach((d, i) => {
      const card = createCard(d);
      if (firstRender && i < 6) { card.classList.add("rise"); card.style.setProperty("--i", i + 3); }
      container.appendChild(card);
    });
    if (!shown.length) {
      container.innerHTML = `<p class="empty">No listings match these filters.</p>`;
    }
    const sortName = sortSelect.options[sortSelect.selectedIndex].text.toLowerCase();
    dealsCount.textContent = `${shown.length} shown of ${listings.length} scanned · by ${sortName}`;

    if (firstRender) {
      hero.classList.add("rise");
      overview.classList.add("rise");
      overview.style.setProperty("--i", 1);
    }
    firstRender = false;
  }

  try {
    const response = await fetch("/api/deals");
    const data = await response.json();
    scannedAt = new Date();
    listings = data.listings.map((d, i) => ({ ...d, _key: i }));
    configMin = data.min_profit;
    // Start the dropdown at the minimum profit from config.py.
    const configValue = String(data.min_profit);
    if (![...minProfitSelect.options].some(o => o.value === configValue)) {
      minProfitSelect.add(new Option("$" + configValue, configValue), 0);
    }
    minProfitSelect.value = configValue;
    searchFilters.innerHTML = data.searches
      .map(s => `<label><input type="checkbox" value="${esc(s)}" checked>${esc(s)}</label>`)
      .join("");
    errorsBox.innerHTML = data.errors.map(e => `<p class="error">${esc(e)}</p>`).join("");
    loadingScreen.hidden = true;
    hero.hidden = false;
    overview.hidden = false;
    dealsHead.hidden = false;
    container.hidden = false;
    render();
  } catch (err) {
    console.error("Error loading deals:", err);
    loadingScreen.innerHTML = '<p class="error">Couldn\'t load deals. Check the terminal running app.py.</p>';
  }

  [hideLow, minProfitSelect, sortSelect].forEach(el => el.addEventListener("change", render));
  searchFilters.addEventListener("change", render);

  // Redraw the chart at the new width.
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (!listings.length) return;
      const shownKeys = new Set([...container.querySelectorAll(".receipt")].map(c => Number(c.dataset.key)));
      drawChart(shownKeys);
    }, 120);
  });
});
