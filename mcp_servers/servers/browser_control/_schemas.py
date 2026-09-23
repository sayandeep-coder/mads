from __future__ import annotations

from mcp import Tool

BROWSER_CONTROL_TOOLS = [
    Tool(
        name="extract_page",
        description=(
            "Read the current browser tab: page title, URL, visible text, and every interactive "
            "element (links, buttons, inputs, selects) tagged with a short `id` like 'e12'. Always "
            "call this first when you land on a new page or after an action changes the page — "
            "the `id`s from a previous extract_page go stale the moment the DOM changes, so never "
            "reuse an old id without re-extracting. Elements that are product links/cards often "
            "carry an `image` field (the product thumbnail URL) — when you present products you "
            "found (e.g. shoe suggestions), include their image as markdown "
            "`![label](image url)` right under each item so Sayan can see what it looks like, not "
            "just the id and price. If the result includes a `warning` field, read it and follow "
            "it exactly — it flags pages (e.g. Google Sheets/Docs) where the extracted text/elements "
            "cannot be trusted or edited through these tools at all."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="navigate",
        description=(
            "Load a URL in the active browser tab (e.g. 'https://www.flipkart.com'). Use this to "
            "go to a site's homepage or a real page you already know the URL of. Do NOT use it to "
            "guess a sub-path like '/cart', '/checkout', or '/account' — on most shopping sites "
            "(Blinkit, Flipkart, Amazon, Zomato, Swiggy, ...) those aren't real pages, they're an "
            "overlay/drawer opened by clicking an icon on the current page, so a guessed URL will "
            "404 or bounce back to the homepage. For anything other than a top-level site, extract_"
            "page the current page and click_element on the actual cart/account/menu icon instead. "
            "Follow up with extract_page once the page loads to see what's on it."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to load, including https://."},
            },
            "required": ["url"],
        },
    ),
    Tool(
        name="click_element",
        description=(
            "Click an element on the current page by the `id` extract_page gave it (e.g. 'e7'). "
            "Use for buttons, links, checkboxes — anything you'd click with a mouse. For a search "
            "box or text field, use type_text instead (it focuses the field for you)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "The element id from the most recent extract_page."},
            },
            "required": ["id"],
        },
    ),
    Tool(
        name="type_text",
        description=(
            "Type text into an input/textarea/search field on the current page, identified by the "
            "`id` extract_page gave it. Replaces whatever is currently in the field. Set "
            "submit=true to also press Enter afterward (e.g. to fire a site's search)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "The input element's id from the most recent extract_page."},
                "text": {"type": "string", "description": "Text to type into the field."},
                "submit": {
                    "type": "boolean",
                    "description": "Press Enter after typing (e.g. to submit a search). Defaults to false.",
                },
            },
            "required": ["id", "text"],
        },
    ),
    Tool(
        name="scroll_to",
        description="Scroll the page so the element with the given id (from extract_page) is in view.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "The element id from the most recent extract_page."},
            },
            "required": ["id"],
        },
    ),
    Tool(
        name="go_back",
        description="Navigate the active tab back one step in its browser history, like pressing the back button.",
        inputSchema={"type": "object", "properties": {}},
    ),
]
