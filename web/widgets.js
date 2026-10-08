// Generic widget behaviour for the page (docs/ui-provenance.md): first
// adapted from the presentation-only app-skeleton.js, now styled by zora.css.
// No option list, no flag logic: zora-web.js supplies those.

// Per-viewer conveniences (the theme, the open tab); memory when storage is blocked.
const widgetMemory = {};
function getSetting(key) {
  try { return localStorage.getItem(key); } catch { return widgetMemory[key] ?? null; }
}
function setSetting(key, value) {
  try { localStorage.setItem(key, value); } catch { widgetMemory[key] = value; }
}

// Light or dark, remembered; follows the system until the viewer chooses.
function initThemeToggle(buttonId = "dark-mode-btn", storageKey = "zora-theme") {
  const button = document.getElementById(buttonId);
  const saved = getSetting(storageKey);
  if (saved) document.documentElement.setAttribute("data-theme", saved);
  const isDark = () => {
    const current = document.documentElement.getAttribute("data-theme");
    return current === "dark" || (!current && window.matchMedia("(prefers-color-scheme: dark)").matches);
  };
  const paint = () => {
    button.textContent = isDark() ? "☀️" : "🌙";
    button.setAttribute("aria-label", isDark() ? "Switch to light theme" : "Switch to dark theme");
  };
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", paint);
  button.addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    setSetting(storageKey, next);
    paint();
  });
  paint();
}

// Pill tabs: buttons with role=tab, each naming its panel in aria-controls.
function initTabs(bar, storageKey = "zora-tab") {
  const tabs = [...bar.querySelectorAll("[role=tab]")];
  const panels = tabs.map((tab) => document.getElementById(tab.getAttribute("aria-controls")));
  const show = (index) => {
    tabs.forEach((tab, i) => {
      tab.setAttribute("aria-selected", String(i === index));
      tab.tabIndex = i === index ? 0 : -1;
      panels[i].hidden = i !== index;
    });
    setSetting(storageKey, tabs[index].id);
  };
  tabs.forEach((tab, i) => tab.addEventListener("click", () => show(i)));
  bar.addEventListener("keydown", (event) => {
    const current = tabs.findIndex((tab) => tab.getAttribute("aria-selected") === "true");
    const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    if (step === undefined) return;
    const next = (current + step + tabs.length) % tabs.length;
    show(next);
    tabs[next].focus();
  });
  const saved = tabs.findIndex((tab) => tab.id === getSetting(storageKey));
  show(saved >= 0 ? saved : 0);
}

// A popover (the colour picker's panel); Escape and a click outside close it.
function initPopover(button, popover, anchor) {
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    popover.hidden = !popover.hidden;
    button.setAttribute("aria-expanded", String(!popover.hidden));
  });
  const close = () => { popover.hidden = true; button.setAttribute("aria-expanded", "false"); };
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") close(); });
  document.addEventListener("click", (event) => { if (!anchor.contains(event.target)) close(); });
  return close;
}

// A "?" help tooltip, centred above its circle (zora.css .tip); moved
// sideways when that would put it past an edge of the window.
function initHelpTip(wrap, tip) {
  const place = () => {
    tip.style.marginLeft = "";
    const box = tip.getBoundingClientRect();
    if (box.width === 0) return;
    const right = document.documentElement.clientWidth - VIEWPORT_MARGIN_PX;
    const shift = box.left < VIEWPORT_MARGIN_PX ? VIEWPORT_MARGIN_PX - box.left
      : box.right > right ? right - box.right : 0;
    if (shift) tip.style.marginLeft = `${shift}px`;
  };
  wrap.addEventListener("mouseenter", place);
  wrap.addEventListener("focusin", place);
}

// The status dot: idle, ready (glowing accent) or error (glowing red).
function setStatusDot(dot, state) {
  dot.className = "status-dot" + (state ? ` status-dot--${state}` : "");
}

// The gap an open colour panel keeps from the window's edge.
const VIEWPORT_MARGIN_PX = 8;

// The swatch-grid colour picker (zora.css): a toggle filled
// with the current colour opens a panel of every palette entry, 16 per row.
// excluded maps an index to the tooltip saying why it cannot be picked; such
// a swatch stays in the grid (aria-disabled, so its tooltip still shows).
// Returns a function that sets the shown value.
function initColorPicker(host, { palette, excluded = {}, value, label, onChange }) {
  const hexCode = (index) => "$" + index.toString(16).toUpperCase().padStart(2, "0");
  const make = (tag, props) => Object.assign(document.createElement(tag), props);
  const picker = make("span", { className: "flag-color-picker" });
  const toggle = make("button", { type: "button", className: "color-picker-toggle color-picker-toggle--color" });
  toggle.setAttribute("aria-haspopup", "true");
  toggle.setAttribute("aria-expanded", "false");
  const panel = make("div", { className: "color-picker-panel", hidden: true });
  const grid = make("div", { className: "color-picker-grid" });
  const swatches = palette.map((rgb, index) => {
    const swatch = make("button", { type: "button", className: "color-swatch" });
    swatch.style.background = rgb;
    if (index in excluded) {
      swatch.classList.add("color-swatch--excluded");
      swatch.setAttribute("aria-disabled", "true");
      swatch.title = excluded[index];
      swatch.setAttribute("aria-label", `${hexCode(index)}: ${excluded[index]}`);
    } else {
      swatch.title = hexCode(index);
      swatch.setAttribute("aria-label", hexCode(index));
      swatch.addEventListener("click", () => { show(index); close(); toggle.focus(); onChange(index); });
    }
    grid.append(swatch);
    return swatch;
  });
  const code = make("span", { className: "color-picker-code" });
  panel.append(grid);
  picker.append(toggle, panel);
  host.append(picker, code);
  const close = initPopover(toggle, panel, picker);
  // The panel opens under the toggle, right-aligned; moved over when that
  // would put it past the left edge of the window.
  toggle.addEventListener("click", () => {
    panel.style.right = "";
    if (panel.hidden) return;
    const overflow = VIEWPORT_MARGIN_PX - panel.getBoundingClientRect().left;
    if (overflow > 0) panel.style.right = `${-overflow}px`;
  });
  function show(index) {
    toggle.style.background = palette[index];
    toggle.setAttribute("aria-label", `${label}: ${hexCode(index)}`);
    code.textContent = hexCode(index);
    swatches.forEach((swatch, i) => swatch.classList.toggle("color-swatch--selected", i === index));
  }
  show(value);
  return show;
}
