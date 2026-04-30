/**
 * Jarvis Eye — Background Service Worker
 * ========================================
 * Manages the WebSocket connection to Jarvis and coordinates
 * between the content script and the Python backend.
 */

const JARVIS_WS_URL = "ws://localhost:9741";
const RECONNECT_DELAY_MS = 3000;

let ws = null;
let isConnected = false;
let reconnectTimer = null;

// ── WebSocket Connection ────────────────────────────────────

function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  try {
    ws = new WebSocket(JARVIS_WS_URL);

    ws.onopen = () => {
      isConnected = true;
      console.log("[Jarvis Eye] Connected to Jarvis");
      clearTimeout(reconnectTimer);
      // Send initial state
      sendActiveTabInfo();
    };

    ws.onmessage = (event) => {
      handleCommand(JSON.parse(event.data));
    };

    ws.onclose = () => {
      isConnected = false;
      console.log("[Jarvis Eye] Disconnected — retrying...");
      scheduleReconnect();
    };

    ws.onerror = (err) => {
      console.error("[Jarvis Eye] WebSocket error:", err);
      ws.close();
    };
  } catch (e) {
    console.error("[Jarvis Eye] Connection failed:", e);
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
}

function send(data) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data));
  }
}

// ── Command Handler ─────────────────────────────────────────

async function handleCommand(data) {
  if (data.type !== "command") return;

  const { requestId, command, params } = data;
  let result = null;

  try {
    switch (command) {
      case "get_page_content":
        result = await executeOnActiveTab(`
          (() => {
            const clone = document.body.cloneNode(true);
            ['script','style','nav','footer','header','.ad'].forEach(sel => {
              clone.querySelectorAll(sel).forEach(el => el.remove());
            });
            return clone.innerText.substring(0, 15000);
          })()
        `);
        break;

      case "get_selected_text":
        result = await executeOnActiveTab(`window.getSelection().toString()`);
        break;

      case "execute_script":
        result = await executeOnActiveTab(params.script);
        break;

      case "inject_css":
        await executeOnActiveTab(`
          (() => {
            const style = document.createElement('style');
            style.textContent = ${JSON.stringify(params.css)};
            document.head.appendChild(style);
          })()
        `);
        result = true;
        break;

      case "get_tab_info":
        const tabs = await chrome.tabs.query({});
        result = tabs.map(t => ({
          id: t.id,
          url: t.url,
          title: t.title,
          active: t.active,
          pinned: t.pinned,
        }));
        break;

      case "focus_tab":
        await chrome.tabs.update(params.tabId, { active: true });
        result = true;
        break;

      case "close_tab":
        await chrome.tabs.remove(params.tabId);
        result = true;
        break;

      case "highlight_element":
        await executeOnActiveTab(`
          (() => {
            const el = document.querySelector(${JSON.stringify(params.selector)});
            if (el) {
              el.style.outline = '3px solid #00d4ff';
              el.style.outlineOffset = '2px';
              setTimeout(() => { el.style.outline = ''; el.style.outlineOffset = ''; }, 3000);
            }
          })()
        `);
        result = true;
        break;

      case "scroll_to":
        await executeOnActiveTab(`window.scrollTo(0, ${params.position || 0})`);
        result = true;
        break;

      default:
        result = { error: `Unknown command: ${command}` };
    }
  } catch (e) {
    result = { error: e.message };
  }

  send({ type: "response", requestId, result });
}

async function executeOnActiveTab(code) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return null;

  const results = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: new Function(`return (${code})`),
  });

  return results[0]?.result || null;
}

// ── Tab Event Monitoring ────────────────────────────────────

chrome.tabs.onActivated.addListener(async (activeInfo) => {
  const tab = await chrome.tabs.get(activeInfo.tabId);
  send({
    type: "tab_event",
    event: "activated",
    tabId: tab.id,
    url: tab.url,
    title: tab.title,
  });
  // Send full page update
  setTimeout(sendActiveTabInfo, 500);
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab.active) {
    send({
      type: "tab_event",
      event: "updated",
      tabId: tab.id,
      url: tab.url,
      title: tab.title,
    });
    setTimeout(sendActiveTabInfo, 500);
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  send({
    type: "tab_event",
    event: "removed",
    tabId,
  });
});

chrome.tabs.onCreated.addListener((tab) => {
  send({
    type: "tab_event",
    event: "created",
    tabId: tab.id,
    url: tab.url || "",
  });
});

// ── Periodic Page State Updates ─────────────────────────────

async function sendActiveTabInfo() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url || tab.url.startsWith("chrome://")) return;

    const allTabs = await chrome.tabs.query({});

    // Get page info from content script
    let pageText = "";
    let selectedText = "";
    let isPlayingMedia = false;
    let scrollPosition = 0;

    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => {
          const text = document.body?.innerText?.substring(0, 5000) || "";
          const selected = window.getSelection()?.toString() || "";
          const media = document.querySelectorAll("video, audio");
          let playing = false;
          media.forEach(m => { if (!m.paused) playing = true; });
          const scrollPos = window.scrollY / (document.body.scrollHeight - window.innerHeight || 1);
          return { text, selected, playing, scrollPos };
        },
      });

      if (results[0]?.result) {
        const r = results[0].result;
        pageText = r.text;
        selectedText = r.selected;
        isPlayingMedia = r.playing;
        scrollPosition = r.scrollPos;
      }
    } catch (e) {
      // Content script might not be injected yet
    }

    send({
      type: "page_update",
      url: tab.url,
      title: tab.title,
      domain: new URL(tab.url).hostname,
      text: pageText,
      selectedText,
      tabCount: allTabs.length,
      isPlayingMedia,
      scrollPosition: Math.min(1, Math.max(0, scrollPosition)),
    });
  } catch (e) {
    // Silently fail (tab might have closed)
  }
}

// Send updates every 5 seconds
setInterval(() => {
  if (isConnected) sendActiveTabInfo();
}, 5000);

// ── Message from Content Script ─────────────────────────────

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message.type === "selection_change") {
    send({
      type: "selection_change",
      text: message.text,
      tabId: sender.tab?.id,
    });
  }
});

// ── Start Connection ────────────────────────────────────────
connect();
