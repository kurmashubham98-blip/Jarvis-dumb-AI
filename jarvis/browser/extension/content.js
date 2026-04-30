/**
 * Jarvis Eye — Content Script
 * =============================
 * Injected into every page. Monitors user activity and
 * reports text selection changes back to the background worker.
 */

// Report text selection changes to background
let lastSelection = "";
document.addEventListener("mouseup", () => {
  const selected = window.getSelection().toString().trim();
  if (selected && selected !== lastSelection) {
    lastSelection = selected;
    chrome.runtime.sendMessage({
      type: "selection_change",
      text: selected,
    });
  }
});

// Also catch keyboard selection
document.addEventListener("keyup", (e) => {
  if (e.shiftKey || e.key === "a" && e.ctrlKey) {
    const selected = window.getSelection().toString().trim();
    if (selected && selected !== lastSelection) {
      lastSelection = selected;
      chrome.runtime.sendMessage({
        type: "selection_change",
        text: selected,
      });
    }
  }
});

// Console tag so user knows Jarvis is watching
console.log(
  "%c[Jarvis Eye] 👁️ Active",
  "color: #00d4ff; font-weight: bold; font-size: 12px;"
);
