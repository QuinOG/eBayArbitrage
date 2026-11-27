// Dark by default. The header button switches to light and remembers the choice.
// Loaded in <head> so the saved theme applies before the page paints.
(function () {
  const root = document.documentElement;
  try {
    if (localStorage.getItem("theme") === "light") root.dataset.theme = "light";
  } catch (e) { /* storage blocked, stay dark */ }

  document.addEventListener("DOMContentLoaded", function () {
    const button = document.getElementById("theme-toggle");
    if (!button) return;
    const sync = () => {
      const light = root.dataset.theme === "light";
      button.setAttribute("aria-label", light ? "Switch to dark" : "Switch to light");
      button.title = light ? "Switch to dark" : "Switch to light";
    };
    sync();
    button.addEventListener("click", () => {
      const light = root.dataset.theme !== "light";
      if (light) root.dataset.theme = "light";
      else delete root.dataset.theme;
      try { localStorage.setItem("theme", light ? "light" : "dark"); } catch (e) { /* ignore */ }
      sync();
      // The chart reads no colors from JS, so CSS variables repaint it on their own.
    });
  });
})();
