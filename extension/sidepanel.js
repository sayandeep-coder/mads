// The side panel is the only piece of the extension that talks to the Mads
// backend: it holds the /ws/browser websocket (relaying each command to
// background.js, which is the one with chrome.tabs/scripting access) and
// drives the chat itself via SSE against /api/browser/chat — same
// SSE-over-fetch pattern the main web app's useChat.ts uses, since
// EventSource can't do POST.

const STORAGE_KEY = "mads_server_url";

const els = {
  statusDot: document.getElementById("status-dot"),
  settingsToggle: document.getElementById("settings-toggle"),
  settingsPanel: document.getElementById("settings-panel"),
  serverUrl: document.getElementById("server-url"),
  connectBtn: document.getElementById("connect-btn"),
  tabChip: document.getElementById("tab-chip"),
  tabChipLabel: document.getElementById("tab-chip-label"),
  tabChipClose: document.getElementById("tab-chip-close"),
  messages: document.getElementById("messages"),
  emptyState: document.getElementById("empty-state"),
  input: document.getElementById("input"),
  sendBtn: document.getElementById("send-btn"),
};

let tabChipDismissed = false;

let socket = null;
let httpBase = "";
let isStreaming = false;

// Auto-reconnect state. The backend restarts fairly often during
// development (picking up code changes) — that closes the socket with
// code 1012 ("service restart") — and even outside dev, a Mac sleep/wake
// or a Wi-Fi blip can drop it. Rather than making Sayan click Connect
// again every time, retry with backoff as long as he hasn't explicitly
// disconnected (there's no manual disconnect button today, but a future
// one, or picking a new server address, should reset this).
let reconnectAttempt = 0;
let reconnectTimer = null;
let manuallyDisconnected = false;
const MAX_RECONNECT_DELAY_MS = 15000;

function setStatus(state, detail) {
  els.statusDot.className = "dot" + (state === "connected" ? " connected" : state === "error" ? " error" : "");
  els.statusDot.title = detail ? `${state}: ${detail}` : state;
}

function wsUrlFromHttp(base) {
  return base.replace(/^http/, "ws").replace(/\/$/, "") + "/ws/browser";
}

// --- Websocket bridge: relays browser_control commands from the backend
// to background.js (which drives the actual tab) and ships the result back. ---

function scheduleReconnect() {
  if (manuallyDisconnected || reconnectTimer) return;
  const delay = Math.min(500 * 2 ** reconnectAttempt, MAX_RECONNECT_DELAY_MS);
  reconnectAttempt += 1;
  setStatus("connecting", `reconnecting in ${Math.round(delay / 1000)}s…`);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectSocket(httpBase, { isRetry: true });
  }, delay);
}

function connectSocket(base, { isRetry = false } = {}) {
  if (!isRetry) {
    manuallyDisconnected = false;
    reconnectAttempt = 0;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  if (socket) {
    try {
      socket.close();
    } catch {
      /* ignore */
    }
  }

  httpBase = base.replace(/\/$/, "");
  const wsUrl = wsUrlFromHttp(httpBase);
  setStatus("connecting", wsUrl);
  console.log("[mads] connecting to", wsUrl);

  let socketInstance;
  try {
    socketInstance = new WebSocket(wsUrl);
  } catch (err) {
    setStatus("error", err instanceof Error ? err.message : String(err));
    console.error("[mads] failed to construct WebSocket:", err);
    scheduleReconnect();
    return;
  }
  socket = socketInstance;

  socket.addEventListener("open", () => {
    reconnectAttempt = 0;
    setStatus("connected", wsUrl);
    console.log("[mads] websocket open");
  });
  socket.addEventListener("close", (event) => {
    setStatus("idle", `closed (code ${event.code}${event.reason ? ": " + event.reason : ""})`);
    console.warn("[mads] websocket closed", event.code, event.reason);
    scheduleReconnect();
  });
  socket.addEventListener("error", (event) => {
    setStatus(
      "error",
      "Could not reach the server — check it's running and the address is correct (see console for details)."
    );
    console.error("[mads] websocket error", event);
  });

  socket.addEventListener("message", async (event) => {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch {
      return;
    }

    const { request_id, action, payload } = message;
    if (!request_id || !action) return;

    try {
      const response = await chrome.runtime.sendMessage({ target: "mads-background", action, payload });
      if (!response) throw new Error("No response from the extension's background worker.");
      if (!response.ok) throw new Error(response.error || "Action failed.");
      socket.send(JSON.stringify({ request_id, ok: true, result: response.result }));
    } catch (err) {
      socket.send(
        JSON.stringify({ request_id, ok: false, error: err instanceof Error ? err.message : String(err) })
      );
    }
  });
}

// --- Chat UI ---

function appendUserMessage(text) {
  els.emptyState.style.display = "none";
  const div = document.createElement("div");
  div.className = "msg user";
  div.innerHTML = `<div class="bubble"></div>`;
  div.querySelector(".bubble").textContent = text;
  els.messages.appendChild(div);
  scrollToBottom();
}

function createAssistantMessage() {
  els.emptyState.style.display = "none";
  const div = document.createElement("div");
  div.className = "msg assistant";

  const thinking = document.createElement("div");
  thinking.className = "thinking";
  thinking.innerHTML = `<span class="thinking-dot"></span><span class="thinking-dot"></span><span class="thinking-dot"></span>`;
  div.appendChild(thinking);

  els.messages.appendChild(div);
  scrollToBottom();
  return {
    root: div,
    thinking,
    toolCalls: new Map(),
    bubble: null,
    // Typewriter reveal state — see pumpTypewriter/finishTypewriter.
    fullText: "",
    shownLength: 0,
    streamDone: false,
    typewriterRunning: false,
    typewriterFrame: null,
  };
}

// Removes the "thinking" placeholder the first time there's something real
// to show in its place (a tool call starting, or the first text delta) —
// so the panel never sits blank while Gemini is working, but also never
// shows a stale spinner once real content exists.
function clearThinking(state) {
  if (state.thinking) {
    state.thinking.remove();
    state.thinking = null;
  }
}

function scrollToBottom() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

const STATUS_ICON_SVG = {
  done: '<svg viewBox="0 0 12 12" width="11" height="11" fill="none"><path d="M2.2 6.3 4.8 9l5-6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  error:
    '<svg viewBox="0 0 12 12" width="11" height="11" fill="none"><path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
};

// Turns a raw tool name like "extract_page" into "Reading the page" —
// short present-progressive labels read like a real "thinking" trace
// instead of exposing internal tool identifiers to Sayan.
const TOOL_LABELS = {
  extract_page: "Reading the page",
  navigate: "Opening the page",
  click_element: "Clicking",
  type_text: "Typing",
  scroll_to: "Scrolling",
  go_back: "Going back",
};

function toolLabel(name) {
  return TOOL_LABELS[name] || name.replace(/_/g, " ");
}

function renderToolCall(state, name, status) {
  let el = state.toolCalls.get(name + status.key);
  if (!el) {
    el = document.createElement("div");
    el.className = "tool-call";
    el.innerHTML = `<span class="status-icon"></span><span class="label"></span>`;
    // Insert tool calls before the text bubble so replies read top-to-bottom.
    state.root.insertBefore(el, state.bubble);
    state.toolCalls.set(name + status.key, el);
  }
  el.className = `tool-call ${status.state}`;
  el.querySelector(".status-icon").innerHTML = STATUS_ICON_SVG[status.state] || "";
  el.querySelector(".label").textContent = toolLabel(status.label);
}

// Small, deliberately narrow markdown renderer — just enough for what the
// agent actually produces (bold, numbered/bulleted lists, product images,
// paragraphs). No library: this is a side-panel page under the extension's
// default CSP, and pulling in a markdown lib for four constructs isn't
// worth the dependency. Escapes HTML first so page content the model
// quotes back can't inject markup into the panel.
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// A GFM-style pipe table row: "| a | b |" (leading/trailing pipes
// optional). The separator row directly under a header row ("|---|---|",
// with optional ':' for alignment) is what confirms it's really a table
// and not just a line that happens to contain pipes.
function parseTableRow(line) {
  if (!line.includes("|")) return null;
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

function isTableSeparatorRow(line) {
  const cells = parseTableRow(line);
  if (!cells || cells.length === 0) return false;
  return cells.every((cell) => /^:?-{2,}:?$/.test(cell));
}

function renderMarkdown(text) {
  const escaped = escapeHtml(text);
  const lines = escaped.split("\n");
  const htmlLines = [];
  let listOpen = null; // "ul" | "ol" | null

  const closeList = () => {
    if (listOpen) {
      htmlLines.push(`</${listOpen}>`);
      listOpen = null;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();

    const imageMatch = line.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);

    if (imageMatch) {
      closeList();
      const [, alt, src] = imageMatch;
      if (/^https?:\/\//.test(src)) {
        htmlLines.push(`<img class="product-image" src="${src}" alt="${alt}" loading="lazy" />`);
      }
      continue;
    }

    if (line.includes("|") && !imageMatch && i + 1 < lines.length && isTableSeparatorRow(lines[i + 1])) {
      closeList();
      const headerCells = parseTableRow(line);
      const headerHtml = headerCells.map((c) => `<th>${applyInlineFormatting(c)}</th>`).join("");
      htmlLines.push(`<table><thead><tr>${headerHtml}</tr></thead><tbody>`);
      i += 1; // skip the separator row

      while (i + 1 < lines.length && lines[i + 1].trim().includes("|")) {
        i += 1;
        const rowCells = parseTableRow(lines[i].trim());
        if (!rowCells) break;
        const rowHtml = rowCells.map((c) => `<td>${applyInlineFormatting(c)}</td>`).join("");
        htmlLines.push(`<tr>${rowHtml}</tr>`);
      }
      htmlLines.push("</tbody></table>");
      continue;
    }

    const bulletMatch = line.match(/^[-*]\s+(.*)$/);
    const numberedMatch = line.match(/^\d+[.)]\s+(.*)$/);

    let inline = null;
    if (bulletMatch) inline = bulletMatch[1];
    else if (numberedMatch) inline = numberedMatch[1];

    if (bulletMatch || numberedMatch) {
      const tag = numberedMatch ? "ol" : "ul";
      if (listOpen !== tag) {
        closeList();
        htmlLines.push(`<${tag}>`);
        listOpen = tag;
      }
      htmlLines.push(`<li>${applyInlineFormatting(inline)}</li>`);
      continue;
    }

    closeList();
    if (line === "") {
      htmlLines.push("<br>");
    } else {
      htmlLines.push(`<p>${applyInlineFormatting(line)}</p>`);
    }
  }
  closeList();

  return htmlLines.join("");
}

function applyInlineFormatting(text) {
  return text
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

function setBubbleText(bubble, text, streaming) {
  bubble.innerHTML = renderMarkdown(text) + (streaming ? '<span class="type-cursor"></span>' : "");
}

// Character-by-character reveal: SSE hands us text in bursts (a whole
// sentence at once, sometimes), not one character per event, so without
// this the "typing" cursor would just jump in chunks. Instead, every
// text_delta only appends to state.fullText — a rAF loop separately drains
// a few characters at a time from fullText into what's actually painted
// (state.shownLength), independent of how the network delivered it, and
// keeps redrawing while there's anything left to reveal even after the
// stream itself has already finished.
const TYPE_CHARS_PER_FRAME = 2;

function pumpTypewriter(state) {
  if (state.typewriterRunning) return;
  state.typewriterRunning = true;

  const step = () => {
    if (state.shownLength < state.fullText.length) {
      state.shownLength = Math.min(state.shownLength + TYPE_CHARS_PER_FRAME, state.fullText.length);
      const stillStreaming = state.shownLength < state.fullText.length || !state.streamDone;
      setBubbleText(ensureBubble(state), state.fullText.slice(0, state.shownLength), stillStreaming);
      scrollToBottom();
      state.typewriterFrame = requestAnimationFrame(step);
    } else if (!state.streamDone) {
      // Caught up to what's arrived so far, but the network stream isn't
      // done yet — keep polling rather than exiting, so a delta that lands
      // a moment later resumes the reveal instead of sitting un-typed.
      state.typewriterFrame = requestAnimationFrame(step);
    } else {
      setBubbleText(ensureBubble(state), state.fullText, false);
      state.typewriterRunning = false;
    }
  };

  state.typewriterFrame = requestAnimationFrame(step);
}

function finishTypewriter(state) {
  state.streamDone = true;
  if (state.typewriterFrame) cancelAnimationFrame(state.typewriterFrame);
  state.typewriterFrame = null;
  state.typewriterRunning = false;
  state.shownLength = state.fullText.length;
  if (state.fullText) setBubbleText(ensureBubble(state), state.fullText, false);
}

function ensureBubble(state) {
  if (!state.bubble) {
    state.bubble = document.createElement("div");
    state.bubble.className = "bubble";
    state.root.appendChild(state.bubble);
  }
  return state.bubble;
}

async function sendMessage(text) {
  if (!text.trim() || isStreaming) return;
  if (!httpBase) {
    alert("Set the Mads server address first (top right), then Connect.");
    return;
  }

  appendUserMessage(text);
  const state = createAssistantMessage();
  isStreaming = true;
  els.sendBtn.disabled = true;

  // A running counter of tool calls with the same name in one turn, so
  // "extract_page" then "click_element" then another "extract_page" each
  // get their own row instead of overwriting one another.
  let callIndex = 0;
  const runningByName = [];

  try {
    const res = await fetch(`${httpBase}/api/browser/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    if (!res.ok || !res.body) throw new Error(`Server responded ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        const dataLine = frame.split("\n").find((l) => l.startsWith("data:"));
        if (!dataLine) continue;
        const json = dataLine.slice("data:".length).trim();
        if (!json) continue;

        let event;
        try {
          event = JSON.parse(json);
        } catch {
          continue;
        }

        if (event.type === "tool_call_started") {
          clearThinking(state);
          const key = callIndex++;
          runningByName.push({ name: event.tool_name, key });
          renderToolCall(state, event.tool_name, { key, state: "running", label: event.tool_name });
        } else if (event.type === "tool_call_finished") {
          const idx = runningByName.findIndex((c) => c.name === event.tool_name);
          const call = idx >= 0 ? runningByName.splice(idx, 1)[0] : { key: callIndex++ };
          renderToolCall(state, event.tool_name, {
            key: call.key,
            state: event.is_error ? "error" : "done",
            label: event.tool_name,
          });
        } else if (event.type === "text_delta") {
          clearThinking(state);
          state.fullText += event.text || "";
          ensureBubble(state);
          pumpTypewriter(state);
        } else if (event.type === "final_response") {
          clearThinking(state);
          if (!state.fullText) state.fullText = event.text || "";
          ensureBubble(state);
          pumpTypewriter(state);
        }
      }
    }
    finishTypewriter(state);
  } catch (err) {
    clearThinking(state);
    finishTypewriter(state);
    state.fullText = `Error: ${err instanceof Error ? err.message : String(err)}`;
    setBubbleText(ensureBubble(state), state.fullText, false);
  } finally {
    clearThinking(state);
    isStreaming = false;
    els.sendBtn.disabled = false;
    scrollToBottom();
  }
}

// --- Active tab chip: mirrors what the extension can currently see/act on,
// same idea as the "Sharing '<tab>'" chip in Chrome's own side panels. ---

function refreshTabChip() {
  if (tabChipDismissed) return;
  chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
    if (!tab || !tab.title) {
      els.tabChip.hidden = true;
      return;
    }
    els.tabChipLabel.textContent = tab.title;
    els.tabChip.hidden = false;
  });
}

if (chrome.tabs?.onActivated) chrome.tabs.onActivated.addListener(refreshTabChip);
if (chrome.tabs?.onUpdated) {
  chrome.tabs.onUpdated.addListener((_id, info) => {
    if (info.status === "complete" || info.title) refreshTabChip();
  });
}
refreshTabChip();

els.tabChipClose.addEventListener("click", () => {
  tabChipDismissed = true;
  els.tabChip.hidden = true;
});

// --- Wiring ---

els.settingsToggle.addEventListener("click", () => {
  els.settingsPanel.hidden = !els.settingsPanel.hidden;
});

document.querySelectorAll(".prompt-pill").forEach((btn) => {
  btn.addEventListener("click", () => {
    const prompt = btn.dataset.prompt || btn.textContent.trim();
    sendMessage(prompt);
  });
});

els.connectBtn.addEventListener("click", () => {
  const base = els.serverUrl.value.trim();
  if (!base) return;
  chrome.storage.local.set({ [STORAGE_KEY]: base });
  connectSocket(base);
});

els.sendBtn.addEventListener("click", () => {
  const text = els.input.value;
  els.input.value = "";
  els.input.style.height = "auto";
  sendMessage(text);
});

els.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    els.sendBtn.click();
  }
});

els.input.addEventListener("input", () => {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 140) + "px";
});

chrome.storage.local.get([STORAGE_KEY], (result) => {
  const saved = result[STORAGE_KEY];
  if (saved) {
    els.serverUrl.value = saved;
    connectSocket(saved);
  }
});
