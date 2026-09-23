// The extension's service worker: owns which tab the agent is currently
// acting on, forwards content-script actions to it, and drives real
// navigation (chrome.tabs.update — a content script can't navigate its own
// tab). The side panel talks to this worker over chrome.runtime messaging;
// this worker never touches the backend websocket itself (the side panel
// page owns that connection, since a service worker can be killed and
// restarted by Chrome at any time and shouldn't be trusted with a live
// socket).

chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});

async function getActiveTabId() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error("No active tab found.");
  return tab.id;
}

async function ensureContentScript(tabId) {
  try {
    await chrome.tabs.sendMessage(tabId, { target: "mads-content", action: "__ping" });
  } catch {
    // Not injected yet (e.g. page loaded before the extension did) — inject now.
    await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
  }
}

async function sendToContentScript(action, payload) {
  const tabId = await getActiveTabId();
  await ensureContentScript(tabId);
  const response = await chrome.tabs.sendMessage(tabId, { target: "mads-content", action, payload });
  if (!response) throw new Error("Content script gave no response.");
  if (!response.ok) throw new Error(response.error || "Content script action failed.");
  return response.result;
}

async function navigate(url) {
  const tabId = await getActiveTabId();
  await chrome.tabs.update(tabId, { url });
  await waitForTabLoad(tabId);
  return { navigated: url };
}

async function goBack() {
  const tabId = await getActiveTabId();
  await chrome.tabs.goBack(tabId);
  await waitForTabLoad(tabId);
  return { wentBack: true };
}

function waitForTabLoad(tabId, timeoutMs = 15000) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    };
    const listener = (updatedTabId, info) => {
      if (updatedTabId === tabId && info.status === "complete") finish();
    };
    chrome.tabs.onUpdated.addListener(listener);
    setTimeout(finish, timeoutMs);
  });
}

// One entry point for every browser_control action the side panel relays
// down from the backend — keeps background.js as the single place that
// knows how each action maps to chrome.* APIs vs. the content script.
async function performAction(action, payload) {
  switch (action) {
    case "extract_page":
      return sendToContentScript("extract_page", {});
    case "click_element":
      return sendToContentScript("click_element", payload);
    case "type_text":
      return sendToContentScript("type_text", payload);
    case "scroll_to":
      return sendToContentScript("scroll_to", payload);
    case "navigate":
      return navigate(payload.url);
    case "go_back":
      return goBack();
    default:
      throw new Error(`Unknown browser action: ${action}`);
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.target !== "mads-background") return;

  performAction(message.action, message.payload || {})
    .then((result) => sendResponse({ ok: true, result }))
    .catch((err) => sendResponse({ ok: false, error: err instanceof Error ? err.message : String(err) }));

  return true; // keep the message channel open for the async response
});
