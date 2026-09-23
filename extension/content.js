// Runs in every page. Exposes the page to the Mads agent as a short,
// stable-for-one-turn list of interactive elements (tagged data-mads-id),
// and executes the primitive actions (click/type/scroll) the agent asks
// for. Talks to background.js via chrome.runtime.onMessage — background.js
// is the one that actually knows which tab is "active" for the agent.

(() => {
  const TAG_ATTR = "data-mads-id";
  const INTERACTIVE_SELECTOR =
    'a[href], button, input, textarea, select, [role="button"], [role="link"], [onclick], [tabindex]';
  // Cap on how many extra cursor:pointer candidates we scan for, so a huge
  // page (thousands of divs) can't make extractPage slow — most real cart/
  // menu icons are near the top of the DOM anyway.
  const MAX_POINTER_CANDIDATES = 4000;

  let idCounter = 0;
  // Bumped on every extract_page call and baked into every id it hands out
  // (as "gN-eM"), so an action against an id from an older extraction is
  // rejected outright rather than silently matching the DOM's current
  // e7/e12/etc — which, on a page that re-renders between calls (a cart
  // drawer opening, a search re-rendering results), can now point at a
  // completely different element than the one the agent meant.
  let generation = 0;

  function isVisible(el) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return false;
    const style = window.getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none" || style.opacity === "0") return false;
    return true;
  }

  function absoluteUrl(src) {
    if (!src) return undefined;
    try {
      return new URL(src, window.location.href).href;
    } catch {
      return undefined;
    }
  }

  function findImageFor(el) {
    // A product link/card usually wraps its thumbnail rather than being an
    // <img> itself, so look inside first; fall back to a nearby ancestor
    // card in case the image is a sibling of the clickable element instead
    // of a descendant (common on sites that wrap image + link separately).
    const inner = el.querySelector?.("img[src]");
    if (inner?.src) return absoluteUrl(inner.currentSrc || inner.src);

    const card = el.closest?.('[class*="product" i], [class*="card" i], li, article');
    const nearby = card?.querySelector?.("img[src]");
    if (nearby?.src) return absoluteUrl(nearby.currentSrc || nearby.src);

    return undefined;
  }

  function describeElement(el) {
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute("role");
    const type = el.getAttribute("type");
    // Icon-only clickables (a bare cart/menu <div>) often carry no direct
    // text or aria-label of their own — fall back to a title/aria-label on
    // an SVG/img child, then any descendant's aria-label, before giving up.
    const label =
      el.getAttribute("aria-label") ||
      el.getAttribute("placeholder") ||
      el.value ||
      el.textContent?.trim().slice(0, 80) ||
      el.querySelector?.("[aria-label]")?.getAttribute("aria-label") ||
      el.querySelector?.("svg title")?.textContent ||
      el.querySelector?.("img[alt]")?.getAttribute("alt") ||
      "";

    return {
      tag,
      role: role || undefined,
      type: type || undefined,
      label: label.replace(/\s+/g, " ").trim(),
      href: tag === "a" ? el.getAttribute("href") || undefined : undefined,
      image: findImageFor(el),
    };
  }

  function findPointerCandidates(alreadyTagged) {
    // Modern SPAs (Blinkit, Flipkart, ...) very often make a plain <div> or
    // <span> clickable purely via a JS event listener with no href/role/
    // onclick attribute at all — invisible to INTERACTIVE_SELECTOR. A
    // computed cursor:pointer style is the one behavioral signal that
    // survives regardless of how the click handler was attached, so scan
    // for it as a fallback rather than missing icon-only buttons like a
    // cart or hamburger menu entirely.
    const candidates = [];
    const all = document.body?.querySelectorAll("div, span, li") || [];
    for (let i = 0; i < all.length && candidates.length < MAX_POINTER_CANDIDATES; i++) {
      const el = all[i];
      if (alreadyTagged.has(el) || el.closest(`[${TAG_ATTR}]`)) continue;
      if (!isVisible(el)) continue;
      if (window.getComputedStyle(el).cursor !== "pointer") continue;
      // Skip a wrapper that merely contains other clickable things — we
      // want the innermost clickable leaf, same as a real click would hit.
      if (el.querySelector('a[href], button, [role="button"]')) continue;
      candidates.push(el);
    }
    return candidates;
  }

  function extractPage() {
    // Fresh tagging pass every call — ids are only ever valid for the
    // extract_page result they came from, by design (see the tool
    // description in mcp_servers/servers/browser_control/_schemas.py), so
    // there's no cost to renumbering everything each time.
    document.querySelectorAll(`[${TAG_ATTR}]`).forEach((el) => el.removeAttribute(TAG_ATTR));
    generation += 1;
    idCounter = 0;

    const elements = [];
    const tagged = new Set();
    document.querySelectorAll(INTERACTIVE_SELECTOR).forEach((el) => {
      if (!isVisible(el)) return;
      const id = `g${generation}-e${idCounter++}`;
      el.setAttribute(TAG_ATTR, id);
      tagged.add(el);
      elements.push({ id, ...describeElement(el) });
    });

    findPointerCandidates(tagged).forEach((el) => {
      const id = `g${generation}-e${idCounter++}`;
      el.setAttribute(TAG_ATTR, id);
      elements.push({ id, ...describeElement(el) });
    });

    const bodyText = document.body?.innerText?.trim().slice(0, 8000) || "";

    return {
      url: window.location.href,
      title: document.title,
      text: bodyText,
      elements,
      warning: isCanvasGridApp()
        ? "This is a canvas-rendered app (Google Sheets/Docs) — extracted text/elements may be " +
          "stale or incomplete, and type_text will not work here at all. Don't attempt to edit " +
          "cells/content via these tools; tell the user to edit it directly instead."
        : undefined,
    };
  }

  function findById(id) {
    const match = /^g(\d+)-e\d+$/.exec(id);
    if (!match || Number(match[1]) !== generation) {
      throw new Error(
        `Id ${id} is from an earlier extract_page call and the page has changed since (this is ` +
          `a different DOM generation) — it cannot be trusted to point at the same element. Call ` +
          `extract_page again and use a fresh id.`
      );
    }

    const el = document.querySelector(`[${TAG_ATTR}="${CSS.escape(id)}"]`);
    if (!el) {
      throw new Error(
        `No element with id ${id} on the current page even though it's from the current extraction ` +
          `— it may have been removed by the page. Call extract_page again.`
      );
    }
    return el;
  }

  function clickElement(id) {
    const el = findById(id);
    el.scrollIntoView({ block: "center", behavior: "instant" });
    el.click();
    return { clicked: id };
  }

  // Canvas-rendered grid/editor apps (Google Sheets, Docs' canvas mode,
  // some drawing/design tools) don't expose their cells as real DOM
  // input/textarea elements at all — what extract_page tags there is a
  // label or a stale/cached readout, never the live cell value, and typing
  // into it via .value + events is a no-op the app never sees. Detecting
  // this up front lets typeText refuse honestly instead of reporting
  // success on an action that changed nothing, which is worse than failing
  // — it was producing confident, wrong "yes it says 8000 now" replies.
  function isCanvasGridApp() {
    const host = window.location.hostname;
    if (/(^|\.)docs\.google\.com$/.test(host)) return true;
    return false;
  }

  function typeText(id, text, submit) {
    if (isCanvasGridApp()) {
      throw new Error(
        "This page (Google Sheets/Docs) renders its content on a canvas, not as real DOM inputs — " +
          "typing into an extracted element id cannot actually change a cell/document here, even if " +
          "the action appears to succeed. Don't retry this and don't report the value as changed; " +
          "tell the user this app isn't supported for typing yet and ask them to edit it directly."
      );
    }

    const el = findById(id);
    el.scrollIntoView({ block: "center", behavior: "instant" });
    el.focus();

    const isRealInput = el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement;
    if (isRealInput) {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
      if (setter) setter.call(el, text);
      else el.value = text;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    } else if (el.isContentEditable) {
      // A contenteditable div (rich-text editors, some chat/comment boxes)
      // has no .value at all — set it via execCommand so the site's own
      // input listeners fire the same as if a person had typed it.
      el.textContent = "";
      document.execCommand("insertText", false, text);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      throw new Error(
        `Element ${id} (<${el.tagName.toLowerCase()}>) isn't a text input, textarea, or editable ` +
          `field — typing into it would silently do nothing. Re-check extract_page for the actual ` +
          `input element, or this page may not support typing here at all.`
      );
    }

    if (submit) {
      el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
      const form = el.closest?.("form");
      if (form) form.requestSubmit ? form.requestSubmit() : form.submit();
    }

    return { typed: id, submitted: !!submit };
  }

  function scrollTo(id) {
    const el = findById(id);
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    return { scrolled: id };
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.target !== "mads-content") return;

    try {
      let result;
      switch (message.action) {
        case "extract_page":
          result = extractPage();
          break;
        case "click_element":
          result = clickElement(message.payload.id);
          break;
        case "type_text":
          result = typeText(message.payload.id, message.payload.text, message.payload.submit);
          break;
        case "scroll_to":
          result = scrollTo(message.payload.id);
          break;
        default:
          sendResponse({ ok: false, error: `Unknown content action: ${message.action}` });
          return;
      }
      sendResponse({ ok: true, result });
    } catch (err) {
      sendResponse({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });
})();
