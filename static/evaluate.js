// "Evaluate a listing" page.
// The server finds the parts and their values. After that, everything here is
// recalculated in the browser as you edit values, add parts, or change the price.

document.addEventListener("DOMContentLoaded", function () {
  const { esc, safeUrl } = window.Parts;
  const linkForm = document.getElementById("link_form");
  const manualForm = document.getElementById("manual_form");
  const titleBox = document.getElementById("title");
  const descriptionBox = document.getElementById("description");
  const priceBox = document.getElementById("price");
  const shippingBox = document.getElementById("shipping");
  const errorBox = document.getElementById("error");
  const result = document.getElementById("result");
  const bench = document.getElementById("bench");

  let taxRate = 0;
  let taxOnShipping = true;
  let lowConfidence = false;

  function money(n) {
    return (n < 0 ? "-$" : "$") + Math.abs(n).toFixed(2);
  }

  function num(input) {
    const n = parseFloat(input.value);
    return isNaN(n) ? 0 : n;
  }

  async function evaluate(body) {
    errorBox.textContent = "";
    result.style.display = "none";
    bench.hidden = true;
    try {
      const response = await fetch("/api/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok) {
        errorBox.textContent = data.error;
        return;
      }
      taxRate = data.sales_tax_rate;
      taxOnShipping = data.tax_on_shipping;
      const d = data.listing;
      // Copy the listing into the form, so you can edit the title and evaluate again.
      titleBox.value = d.title;
      descriptionBox.value = (d.description || []).join("\n");
      priceBox.value = d.price.toFixed(2);
      shippingBox.value = d.shipping.toFixed(2);
      showResult(d, data.min_profit);
    } catch (err) {
      console.error(err);
      errorBox.textContent = "Something went wrong. Check the terminal running app.py.";
    }
  }

  function partRow(name, model, detail, value, low) {
    return `
      <tr class="part-row ${low ? "low-row" : ""}">
        <td>${esc(name)}</td>
        <td>${model}<div class="part-data"><span class="dot ${low ? "low" : "high"}"></span>${esc(detail)}</div></td>
        <td class="num"><input class="value" type="number" step="0.01" value="${value.toFixed(2)}"></td>
        <td><button type="button" class="remove" title="Remove this part" aria-label="Remove this part">×</button></td>
      </tr>`;
  }

  // Detail line under a priced part: sales, confidence, how it was priced, and where it was found.
  function partDetail(p) {
    const how = p.kind === "fallback" ? `fallback: ${p.priced_as}` : p.kind;
    const base = p.kind === "no data" ? "no price data, type a value" : `${p.sales} sales · ${p.confidence} · ${how}`;
    return p.source && p.source !== "title" ? `${base} · from ${p.source}` : base;
  }

  // Part types for the "Add part" row. The first four are priced from data/prices.csv.
  const PRICED = { cpu: "CPU", mobo: "Motherboard", ram: "RAM", gpu: "GPU" };
  const OTHER = ["Cooler", "PSU", "Storage", "Case", "Other"];

  function addPartRow() {
    const options = Object.entries(PRICED).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")
      + OTHER.map(n => `<option value="">${n}</option>`).join("");
    return `
      <tr class="part-row added">
        <td><select class="part-type">${options}</select></td>
        <td><input class="part-name" type="text" placeholder="Model, e.g. RTX 3060 12GB">
            <div class="part-data"><span class="dot high"></span><span class="lookup">type a model and press Enter</span></div></td>
        <td class="num"><input class="value" type="number" step="0.01" value="0.00"></td>
        <td><button type="button" class="remove" title="Remove this part" aria-label="Remove this part">×</button></td>
      </tr>`;
  }

  // Look up a typed CPU, board, RAM or GPU in prices.csv and fill in its value.
  async function lookupRow(row) {
    const part = row.querySelector(".part-type").value;
    const text = row.querySelector(".part-name").value.trim();
    const note = row.querySelector(".lookup");
    if (!part) {
      note.textContent = "no price data for this type, type a value";
      return;
    }
    if (!text) return;
    note.textContent = "looking up...";
    const response = await fetch("/api/price", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ part, text }),
    });
    const p = await response.json();
    const low = !response.ok || p.confidence !== "high";
    row.classList.toggle("low-row", low);
    row.querySelector(".dot").className = "dot " + (low ? "low" : "high");
    if (!response.ok) {
      note.textContent = p.error;
      return;
    }
    note.textContent = `${p.model} · ${partDetail(p)}`;
    row.querySelector(".value").value = p.value.toFixed(2);
    recalc();
  }

  function showResult(d, minProfit) {
    const rows = d.parts.map(p => partRow(p.name, esc(p.model), partDetail(p), p.value, p.confidence !== "high"));
    d.missing.forEach(m => rows.push(partRow(m.name, '<span class="unknown">not identified</span>', "type a value, or remove", 0, true)));
    (d.extras || []).forEach(e => rows.push(partRow(e.name, esc(e.model),
      `no price data, type a value${e.source !== "title" ? " · from " + e.source : ""}`, 0, true)));

    const link = d.listing_url
      ? `<a href="${safeUrl(d.listing_url)}" target="_blank" rel="noopener">${esc(d.title)}</a>`
      : esc(d.title);
    const flags = d.flags.length
      ? `<ul class="flags">${d.flags.map(f => `<li>${esc(f)}</li>`).join("")}</ul>`
      : "";

    result.innerHTML = `
      <div class="r-head">
        <div id="stamp"></div>
        <p class="r-meta">${esc(d.condition || "Entered by hand")}</p>
        <h2>${link}</h2>
      </div>
      <div class="spread" id="spread" aria-hidden="true"></div>
      <table class="parts">
        <tbody id="part_rows">${rows.join("")}</tbody>
        <tr><td colspan="4"><button type="button" id="add_part">Add part: GPU, cooler, PSU, storage...</button></td></tr>
        <tr class="total"><td colspan="2">Parts value</td><td class="num" id="parts_value"></td><td></td></tr>
        <tr><td colspan="2"><i class="sw seg-price"></i>Price, try an offer</td>
            <td class="num"><input id="r_price" type="number" step="0.01" value="${d.price.toFixed(2)}"></td><td></td></tr>
        <tr><td colspan="2"><i class="sw seg-shipping"></i>Shipping</td>
            <td class="num"><input id="r_shipping" type="number" step="0.01" value="${d.shipping.toFixed(2)}"></td><td></td></tr>
        <tr><td colspan="2"><i class="sw seg-tax"></i>Sales tax (${(taxRate * 100).toFixed(2)}%)</td><td class="num" id="tax"></td><td></td></tr>
        <tr class="total profit-row"><td colspan="2"><i class="sw seg-profit"></i>Profit</td><td class="num" id="profit"></td><td></td></tr>
      </table>
      <p class="max-price">
        For <input id="target" type="number" step="1" value="${minProfit}"> profit, pay at most
        <strong id="max_price"></strong>
      </p>
      ${flags}`;
    result.style.display = "block";
    lowConfidence = d.confidence === "low";

    // The identified parts, drawn on the bench with their sold prices.
    const drawn = d.parts.filter(p => p.model);
    bench.hidden = !drawn.length;
    bench.innerHTML = drawn.length
      ? `<figcaption class="bench-caption"><span>Parts found in the listing</span></figcaption>
         <div class="bench-items">${window.Parts.items(drawn)}</div>`
      : "";

    // Buttons add and remove part rows.
    result.querySelector("#add_part").addEventListener("click", () => {
      const tbody = result.querySelector("#part_rows");
      tbody.insertAdjacentHTML("beforeend", addPartRow());
      const row = tbody.lastElementChild;
      const name = row.querySelector(".part-name");
      name.addEventListener("change", () => lookupRow(row));
      name.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); name.blur(); } });
      row.querySelector(".part-type").addEventListener("change", () => lookupRow(row));
      name.focus();
      recalc();
    });
    result.querySelector("#part_rows").addEventListener("click", e => {
      if (e.target.classList.contains("remove")) {
        e.target.closest("tr").remove();
        recalc();
      }
    });
    recalc();
  }

  // Spread bar: the parts value split into price, shipping, tax and what you keep.
  // On a loss the bar is the cost, with a red tick where the parts value runs out.
  function drawSpread(value, price, shipping, tax, profit) {
    const segs = [["price", price], ["shipping", shipping], ["tax", tax], ["profit", Math.max(0, profit)]]
      .filter(s => s[1] > 0)
      .map(([k, v]) => `<span class="seg seg-${k}" style="flex-grow:${v}"></span>`)
      .join("");
    const spent = price + shipping + tax;
    const mark = profit < 0 && spent > 0
      ? `<span class="spread-mark" style="left:${(Math.max(0, value) / spent) * 100}%"></span>`
      : "";
    result.querySelector("#spread").innerHTML = segs + mark;
  }

  function recalc() {
    const value = [...result.querySelectorAll("#part_rows .value")].reduce((sum, input) => sum + num(input), 0);
    const price = num(result.querySelector("#r_price"));
    const shipping = num(result.querySelector("#r_shipping"));
    const tax = Math.round((taxOnShipping ? price + shipping : price) * taxRate * 100) / 100;
    const profit = value - price - shipping - tax;
    const target = num(result.querySelector("#target"));

    // Highest price that still leaves the target profit after shipping and tax.
    const maxPrice = taxOnShipping
      ? (value - target) / (1 + taxRate) - shipping
      : (value - target - shipping) / (1 + taxRate);

    result.querySelector("#parts_value").textContent = money(value);
    result.querySelector("#tax").textContent = tax ? money(-tax) : money(0);
    const profitCell = result.querySelector("#profit");
    profitCell.textContent = money(profit);
    profitCell.className = "num " + (profit >= target ? "good" : "bad");
    result.classList.toggle("no-deal-card", profit < target);
    result.querySelector("#stamp").outerHTML = profit < 0
      ? `<div id="stamp" class="stamp pass"><b>Pass</b><span>${money(profit)}</span></div>`
      : profit >= target
        ? `<div id="stamp" class="stamp ${lowConfidence ? "check" : "buy"}"><b>${lowConfidence ? "Check" : "Buy"}</b><span>+${money(profit)}</span></div>`
        : `<div id="stamp" class="r-verdict">+${money(profit)}<span>under $${target}</span></div>`;
    drawSpread(value, price, shipping, tax, profit);
    result.querySelector("#max_price").textContent = maxPrice > 0
      ? money(Math.floor(maxPrice * 100) / 100)
      : "nothing works, parts are worth less than shipping plus target";
  }

  // Any edit to a number in the result recalculates the profit.
  result.addEventListener("input", recalc);

  linkForm.addEventListener("submit", e => {
    e.preventDefault();
    evaluate({ link: document.getElementById("link").value });
  });

  manualForm.addEventListener("submit", e => {
    e.preventDefault();
    evaluate({ title: titleBox.value, description: descriptionBox.value, price: priceBox.value, shipping: shippingBox.value });
  });
});
