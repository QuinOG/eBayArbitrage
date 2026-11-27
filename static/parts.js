// Drawings of the parts a listing contains, for the bench on both pages.
// Each part gets a top-down SVG (CPU, RAM, GPU, motherboard) and a paper price tag
// with its sold price from data/prices.csv.

window.Parts = (function () {
  function esc(text) {
    const div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  }

  function money(n) {
    const abs = Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return (n < 0 ? "-$" : "$") + abs;
  }

  // Shared gradients, added to the page once.
  const DEFS = `
    <svg width="0" height="0" style="position:absolute" aria-hidden="true">
      <defs>
        <linearGradient id="p-ihs" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#f4f3ef"/><stop offset=".42" stop-color="#cfd0d0"/>
          <stop offset=".5" stop-color="#e4e4e1"/><stop offset="1" stop-color="#a7a9ab"/>
        </linearGradient>
        <linearGradient id="p-pcb" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#2f6a45"/><stop offset="1" stop-color="#1f4d31"/>
        </linearGradient>
        <linearGradient id="p-board" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#2c3036"/><stop offset="1" stop-color="#1c1f23"/>
        </linearGradient>
        <linearGradient id="p-gold" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#f0cf72"/><stop offset="1" stop-color="#b8862b"/>
        </linearGradient>
        <linearGradient id="p-alu" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#d9dadb"/><stop offset=".5" stop-color="#9fa2a6"/><stop offset="1" stop-color="#c4c6c8"/>
        </linearGradient>
        <linearGradient id="p-shroud" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#3d3e42"/><stop offset="1" stop-color="#202124"/>
        </linearGradient>
        <radialGradient id="p-fan" cx=".5" cy=".5" r=".5">
          <stop offset=".3" stop-color="#2a2b2e"/><stop offset="1" stop-color="#141416"/>
        </radialGradient>
      </defs>
    </svg>`;

  function ensureDefs() {
    if (!document.getElementById("p-ihs")) document.body.insertAdjacentHTML("afterbegin", DEFS);
  }

  function brand(model) {
    const m = model.toLowerCase();
    if (/ryzen|athlon|threadripper|\bfx\b|radeon|\brx\b/.test(m)) return "AMD";
    if (/core|i[3579]-|xeon|pentium|celeron|\barc\b/.test(m)) return "INTEL";
    if (/gtx|rtx|quadro/.test(m)) return "NVIDIA";
    return "";
  }

  function clip(text, n) {
    return text.length > n ? text.slice(0, n - 1) + "…" : text;
  }

  // CPU, top view: green substrate, nickel heat spreader, etched model.
  function cpu(model) {
    const pads = Array.from({ length: 9 }, (_, i) =>
      `<rect x="${20 + i * 9}" y="7" width="4" height="3" rx=".5" fill="url(#p-gold)"/>
       <rect x="${20 + i * 9}" y="110" width="4" height="3" rx=".5" fill="url(#p-gold)"/>`).join("");
    return `
      <svg class="obj" viewBox="0 0 120 120" style="--w:116px">
        <rect x="2" y="2" width="116" height="116" rx="6" fill="url(#p-pcb)"/>
        ${pads}
        <path d="M5 115 h9 l-9 -9z" fill="url(#p-gold)"/>
        <rect x="15" y="15" width="90" height="90" rx="9" fill="url(#p-ihs)"/>
        <rect x="15.5" y="15.5" width="89" height="89" rx="8.5" fill="none" stroke="rgba(0,0,0,.18)"/>
        <path d="M22 22 L98 98" stroke="rgba(255,255,255,.35)" stroke-width="10"/>
        <text class="etch" x="60" y="55" text-anchor="middle" font-size="8">${esc(brand(model))}</text>
        <text class="etch" x="60" y="67" text-anchor="middle" font-size="6.5">${esc(clip(model.toUpperCase(), 18))}</text>
      </svg>`;
  }

  // RAM stick: green PCB, black packages, gold contacts, a paper label.
  function ram(model) {
    const contacts = [];
    for (let x = 6; x < 196; x += 3.4) {
      if (x > 104 && x < 114) continue; // the key notch
      contacts.push(`<rect x="${x.toFixed(1)}" y="38" width="2.2" height="9" rx=".4" fill="url(#p-gold)"/>`);
    }
    const chips = Array.from({ length: 6 }, (_, i) =>
      `<rect x="${8 + i * 21}" y="9" width="17" height="20" rx="1" fill="#1b1b1d"/>
       <rect x="${8 + i * 21}" y="9" width="17" height="2" rx="1" fill="#3a3a3e"/>`).join("");
    const [size, ...rest] = model.split(" ");
    return `
      <svg class="obj" viewBox="0 0 200 48" style="--w:220px">
        <path d="M3 0 H197 a3 3 0 0 1 3 3 V48 H114 v-5 a3 3 0 0 0 -6 0 v5 H0 V3 a3 3 0 0 1 3 -3z" fill="url(#p-pcb)"/>
        ${chips}${contacts.join("")}
        <rect x="136" y="7" width="58" height="24" rx="2" fill="#f6f3ea"/>
        <text class="label" x="141" y="17" font-size="7.5">${esc(clip(size, 10))}</text>
        <text class="label dim" x="141" y="26" font-size="5.5">${esc(clip(rest.join(" "), 16))}</text>
      </svg>`;
  }

  // Graphics card: dark shroud, two fans, PCIe fingers.
  function gpu(model) {
    const blades = (cx, cy) => Array.from({ length: 9 }, (_, i) =>
      `<path d="M0 -8 C7 -11 12 -19 8 -27 L3 -27 C5 -19 2 -13 -3 -8Z" fill="#2d2e32"
              transform="translate(${cx} ${cy}) rotate(${i * 40})"/>`).join("");
    const fingers = Array.from({ length: 30 }, (_, i) =>
      i === 8 ? "" : `<rect x="${44 + i * 3.6}" y="88" width="2.4" height="9" rx=".4" fill="url(#p-gold)"/>`).join("");
    return `
      <svg class="obj" viewBox="0 0 220 98" style="--w:236px">
        <rect x="36" y="80" width="116" height="10" fill="#1f4d31"/>
        ${fingers}
        <rect x="0" y="0" width="220" height="84" rx="9" fill="url(#p-shroud)"/>
        <rect x="0.5" y="0.5" width="219" height="83" rx="8.5" fill="none" stroke="rgba(255,255,255,.08)"/>
        <circle cx="62" cy="42" r="33" fill="url(#p-fan)"/><circle cx="158" cy="42" r="33" fill="url(#p-fan)"/>
        ${blades(62, 42)}${blades(158, 42)}
        <circle cx="62" cy="42" r="9" fill="#232427" stroke="#3b3c40"/><circle cx="158" cy="42" r="9" fill="#232427" stroke="#3b3c40"/>
        <text class="etch light" x="110" y="80" text-anchor="middle" font-size="5.5">${esc(clip(model.toUpperCase(), 22))}</text>
      </svg>`;
  }

  // Motherboard, top view: socket, DIMM slots, heatsinks, PCIe slots.
  function board(model) {
    const dimms = Array.from({ length: 4 }, (_, i) =>
      `<rect x="${96 + i * 8}" y="14" width="4.5" height="70" rx="1" fill="#15171a" stroke="#3a3e44" stroke-width=".6"/>`).join("");
    const traces = Array.from({ length: 6 }, (_, i) =>
      `<path d="M${74} ${36 + i * 5} H${92}" stroke="#3a4048" stroke-width=".6"/>`).join("");
    return `
      <svg class="obj" viewBox="0 0 140 160" style="--w:150px">
        <rect x="0" y="0" width="140" height="160" rx="4" fill="url(#p-board)"/>
        ${traces}
        <rect x="8" y="8" width="16" height="70" rx="2" fill="url(#p-alu)"/>
        <rect x="28" y="8" width="56" height="12" rx="2" fill="url(#p-alu)"/>
        <rect x="32" y="28" width="40" height="44" rx="2" fill="#dcd8cc"/>
        <rect x="38" y="34" width="28" height="32" rx="1" fill="#c9c4b6"/>
        ${dimms}
        <rect x="8" y="96" width="96" height="6" rx="1" fill="#15171a" stroke="#3a3e44" stroke-width=".6"/>
        <rect x="8" y="118" width="62" height="5" rx="1" fill="#15171a" stroke="#3a3e44" stroke-width=".6"/>
        <rect x="96" y="108" width="34" height="34" rx="3" fill="url(#p-alu)"/>
        <text class="etch light" x="8" y="152" font-size="6">${esc(clip(model.toUpperCase(), 22))}</text>
      </svg>`;
  }

  function draw(part) {
    const model = part.model || part.name;
    if (part.name === "CPU") return cpu(model);
    if (part.name === "RAM") return ram(model);
    if (part.name === "GPU") return gpu(model);
    if (part.name === "Motherboard") return board(model);
    return "";
  }

  function tag(part) {
    const low = part.confidence !== "high";
    const sold = part.kind === "no data" ? "no sold data" : `${part.sales} sold`;
    return `
      <div class="tag ${low ? "low" : ""}">
        <span class="tag-name">${esc(part.model || part.name)}</span>
        <span class="tag-price">${money(part.value)}</span>
        <span class="tag-sold">${esc(sold)}${low ? " · check" : ""}</span>
      </div>`;
  }

  // The parts laid out on the bench, each with its price tag hanging below.
  // Fewer parts are drawn bigger, so a lone CPU still fills the bench.
  function items(parts) {
    ensureDefs();
    const order = { GPU: 0, Motherboard: 1, CPU: 2, RAM: 3 };
    const scale = parts.length === 1 ? 1.7 : parts.length === 2 ? 1.3 : 1;
    return `<div class="bench-row" style="--scale:${scale}">` + parts.slice()
      .sort((a, b) => (order[a.name] ?? 9) - (order[b.name] ?? 9))
      .map((p, i) => `
        <div class="bench-item" style="--tilt:${[-3, 2, -1.5, 2.5][i % 4]}deg">
          ${draw(p)}
          <span class="string"></span>
          ${tag(p)}
        </div>`).join("") + `</div>`;
  }

  return { items, money, esc };
})();
