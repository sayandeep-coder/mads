// The Mads Excel task pane. Unlike the Chrome extension's side panel
// (which needs a background service worker to reach a separate browser
// tab), this page runs *inside* the same Office process as the workbook,
// so it can call Excel.run() directly — no relay needed for the Excel
// actions themselves. It still holds a websocket to the backend (same
// WebSocketCommandBridge pattern as browser_control) because the agent
// runs server-side and needs a way to ask "what's in this workbook" and
// wait for a real answer, exactly like the browser case.

/* global Office, Excel */

const STORAGE_KEY = "mads_server_url";

const els = {
  statusDot: document.getElementById("status-dot"),
  settingsToggle: document.getElementById("settings-toggle"),
  settingsPanel: document.getElementById("settings-panel"),
  serverUrl: document.getElementById("server-url"),
  connectBtn: document.getElementById("connect-btn"),
  messages: document.getElementById("messages"),
  emptyState: document.getElementById("empty-state"),
  input: document.getElementById("input"),
  sendBtn: document.getElementById("send-btn"),
};

let socket = null;
let httpBase = "";
let isStreaming = false;

let reconnectAttempt = 0;
let reconnectTimer = null;
let manuallyDisconnected = false;
const MAX_RECONNECT_DELAY_MS = 15000;

function setStatus(state, detail) {
  els.statusDot.className = "dot" + (state === "connected" ? " connected" : state === "error" ? " error" : "");
  els.statusDot.title = detail ? `${state}: ${detail}` : state;
}

function wsUrlFromHttp(base) {
  return base.replace(/^http/, "ws").replace(/\/$/, "") + "/ws/excel";
}

// --- Excel actions: the only place in this file that touches Excel.run().
// Each function mirrors one excel_control tool 1:1 (see
// mcp_servers/servers/excel_control/_schemas.py) — the agent decides which
// to call and with what arguments; this file just executes it against the
// real open workbook and reports back what happened. ---

async function listSheets() {
  return Excel.run(async (context) => {
    const sheets = context.workbook.worksheets;
    sheets.load("items/name,items/position");
    const activeSheet = context.workbook.worksheets.getActiveWorksheet();
    activeSheet.load("name");
    await context.sync();

    return {
      sheets: sheets.items.map((s) => ({ name: s.name, position: s.position })),
      active_sheet: activeSheet.name,
    };
  });
}

function splitRange(range_) {
  const bangIndex = range_.lastIndexOf("!");
  if (bangIndex === -1) return { sheetName: null, address: range_ };
  return { sheetName: range_.slice(0, bangIndex), address: range_.slice(bangIndex + 1) };
}

// Excel.Range.getRange() only accepts real A1 cell addresses ("A1:D20") —
// it does NOT understand whole-row/column shorthand like "2:2" or "A:A"
// (the agent tried exactly that and got nothing back, which is this bug).
// Detect that shorthand and translate it into the sheet's actual used
// range for that row/column, so an address the agent might reasonably
// send still resolves to something real instead of silently failing.
function isRowOrColumnShorthand(address) {
  return /^\d+:\d+$/.test(address) || /^[A-Za-z]+:[A-Za-z]+$/.test(address);
}

function getRangeObject(context, range_) {
  const { sheetName, address } = splitRange(range_);
  const sheet = sheetName ? context.workbook.worksheets.getItem(sheetName) : context.workbook.worksheets.getActiveWorksheet();

  if (isRowOrColumnShorthand(address)) {
    const isRow = /^\d+:\d+$/.test(address);
    const used = sheet.getUsedRangeOrNullObject();
    return { sheet, address, isRowOrColumnShorthand: true, isRow, usedRange: used };
  }

  return { sheet, range: sheet.getRange(address) };
}

async function resolveRange(context, range_) {
  const resolved = getRangeObject(context, range_);
  if (!resolved.isRowOrColumnShorthand) return resolved.range;

  resolved.usedRange.load("rowIndex,columnIndex,rowCount,columnCount");
  await context.sync();
  if (resolved.usedRange.isNullObject) {
    throw new Error(`Sheet has no data at all, so "${resolved.address}" has nothing to read.`);
  }

  const rowNum = parseInt(resolved.address.split(":")[0], 10);
  if (resolved.isRow) {
    // "2:2" -> row 2 across the sheet's actual used columns, not a literal
    // whole-row read (Office.js has no direct API for an unbounded row).
    return resolved.sheet.getRangeByIndexes(
      rowNum - 1,
      resolved.usedRange.columnIndex,
      1,
      resolved.usedRange.columnCount
    );
  }
  throw new Error(`Column-only range "${resolved.address}" isn't supported yet — use a full address like "A1:A1000".`);
}

async function readRange(range_) {
  return Excel.run(async (context) => {
    const range = await resolveRange(context, range_);
    range.load("values,address,worksheet/name");
    await context.sync();

    // If the requested range is empty, tell the caller what the sheet's
    // real used range is instead of just handing back an empty grid —
    // that's the one piece of information that actually resolves "why is
    // this empty" without another guess-and-check round trip.
    const isEmpty = range.values.every((row) => row.every((cell) => cell === "" || cell === null));
    let usedRangeHint;
    if (isEmpty) {
      const used = range.worksheet.getUsedRangeOrNullObject();
      used.load("address");
      await context.sync();
      usedRangeHint = used.isNullObject ? "The sheet has no data at all." : `Sheet's actual used range is ${used.address}.`;
    }

    return {
      address: range.address,
      sheet: range.worksheet.name,
      values: range.values,
      ...(usedRangeHint ? { note: usedRangeHint } : {}),
    };
  });
}

async function writeRange(range_, values) {
  return Excel.run(async (context) => {
    const range = await resolveRange(context, range_);
    range.values = values;
    range.load("address,worksheet/name");
    await context.sync();

    return {
      address: range.address,
      sheet: range.worksheet.name,
      written: true,
    };
  });
}

async function getSelection() {
  return Excel.run(async (context) => {
    const range = context.workbook.getSelectedRange();
    range.load("values,address,worksheet/name");
    await context.sync();

    return {
      address: range.address,
      sheet: range.worksheet.name,
      values: range.values,
    };
  });
}

async function addSheet(name) {
  return Excel.run(async (context) => {
    const sheet = context.workbook.worksheets.add(name);
    sheet.activate();
    sheet.load("name");
    await context.sync();

    return { added: sheet.name };
  });
}

async function performExcelAction(action, payload) {
  switch (action) {
    case "list_sheets":
      return listSheets();
    case "read_range":
      return readRange(payload.range_);
    case "write_range":
      return writeRange(payload.range_, payload.values);
    case "get_selection":
      return getSelection();
    case "add_sheet":
      return addSheet(payload.name);
    default:
      throw new Error(`Unknown excel_control action: ${action}`);
  }
}

// --- Websocket bridge: relays excel_control commands from the backend to
// performExcelAction and ships the result back, same request/response
// shape server.browser_bridge.WebSocketCommandBridge expects. ---

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
      const result = await performExcelAction(action, payload || {});
      socket.send(JSON.stringify({ request_id, ok: true, result }));
    } catch (err) {
      socket.send(JSON.stringify({ request_id, ok: false, error: describeExcelError(err) }));
    }
  });
}

// Office.js API failures come back as OfficeExtension.Error objects, whose
// .message is often generic ("An unexpected error occurred") while the
// actually useful detail lives in .code and .debugInfo.message — surface
// all of it so a failed tool call reports something the agent (and Sayan)
// can act on, instead of a vague "something went wrong".
function describeExcelError(err) {
  if (err && typeof err === "object") {
    const parts = [];
    if (err.code) parts.push(`[${err.code}]`);
    if (err.message) parts.push(err.message);
    if (err.debugInfo?.message && err.debugInfo.message !== err.message) parts.push(err.debugInfo.message);
    if (parts.length) return parts.join(" ");
  }
  return err instanceof Error ? err.message : String(err);
}

// --- Chat UI (identical pattern to the Chrome extension's sidepanel.js) ---

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
    fullText: "",
    shownLength: 0,
    streamDone: false,
    typewriterRunning: false,
    typewriterFrame: null,
  };
}

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

const TOOL_LABELS = {
  list_sheets: "Checking sheets",
  read_range: "Reading cells",
  write_range: "Writing cells",
  get_selection: "Checking your selection",
  add_sheet: "Adding a sheet",
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
    state.root.insertBefore(el, state.bubble);
    state.toolCalls.set(name + status.key, el);
  }
  el.className = `tool-call ${status.state}`;
  el.querySelector(".status-icon").innerHTML = STATUS_ICON_SVG[status.state] || "";
  el.querySelector(".label").textContent = toolLabel(status.label);
}

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
  let listOpen = null;

  const closeList = () => {
    if (listOpen) {
      htmlLines.push(`</${listOpen}>`);
      listOpen = null;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();

    if (line.includes("|") && i + 1 < lines.length && isTableSeparatorRow(lines[i + 1])) {
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

  let callIndex = 0;
  const runningByName = [];

  try {
    const res = await fetch(`${httpBase}/api/excel/chat`, {
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
  localStorage.setItem(STORAGE_KEY, base);
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

// Office add-ins must wait for Office.onReady before touching Office.js
// APIs (Excel.run included) — the host may not have finished initializing
// the JS runtime bridge yet, and calling in too early fails silently on
// some hosts.
Office.onReady(() => {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) {
    els.serverUrl.value = saved;
    connectSocket(saved);
  }
});
