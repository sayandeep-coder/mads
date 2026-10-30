import type { ChatMessage, GeneratedFile } from "@/lib/types";
import { Fragment, type ReactNode, useEffect, useRef, useState } from "react";
import { DownloadChip } from "./DownloadChip";
import { ToolCallRow } from "./ToolCallRow";

// One character revealed roughly every this many milliseconds — paced by
// wall-clock time (via performance.now(), see below), not by counting
// animation frames, so the speed is the same regardless of frame rate.
const MS_PER_CHAR = 20;

// Above this length, skip the per-character animation and render the
// reply directly. A long reply (a big markdown table, a detailed
// multi-paragraph summary) re-parsing itself from scratch on every single
// added character is real, unbounded work that piles up over the whole
// reveal — for a few hundred characters that's cheap, for several
// thousand it can be enough sustained main-thread work to crash the tab's
// renderer outright. Real chat products cap animated reveal to short
// replies for exactly this reason; a long reply reads fine appearing at
// once, nobody needs to watch a 3,000-character answer type out letter by
// letter anyway.
const MAX_ANIMATED_LENGTH = 600;

// Mirrors server/code_runner.py's _LANGUAGE_RUNNERS keys — a code block
// only gets a Run button if the backend actually knows how to execute it.
const RUNNABLE_LANGUAGES = new Set([
  "python",
  "py",
  "javascript",
  "js",
  "node",
  "typescript",
  "ts",
  "bash",
  "sh",
  "shell",
]);

/**
 * Reveals `fullText` one character at a time, independent of how large the
 * chunks were that actually arrived over the network (Gemini streams whole
 * sentences at once, not one character per event — painting each chunk
 * verbatim looks like words popping in, not typing) and independent of
 * whether the network stream itself has already finished — a reply that
 * arrives in one fast burst still types out at a fixed pace instead of
 * animating for a moment and then snapping the rest in the instant
 * `streamDone` flips true.
 *
 * `enabled` only controls whether this message should animate AT ALL
 * (false for a message that was already complete when it first rendered,
 * e.g. loaded from history) — once animation starts for a message it runs
 * to completion on its own schedule and is never interrupted or
 * fast-forwarded by fullText's growth or the stream ending.
 *
 * A single requestAnimationFrame loop per mounted message, driven by
 * elapsed wall-clock time rather than a fixed-interval timer — this keeps
 * exactly one live callback per message (no per-tick setInterval churn as
 * fullText grows), self-terminates the instant it catches up, and is
 * always torn down on unmount via the effect cleanup, so a long
 * conversation can never accumulate stray, uncleared timers.
 */
function useTypewriter(fullText: string, enabled: boolean): string {
  const [shownLength, setShownLength] = useState(() => (enabled ? 0 : fullText.length));
  const everEnabledRef = useRef(enabled);
  if (enabled) everEnabledRef.current = true;
  // Latches permanently once true — a reply that grows past the cap while
  // still streaming stays in "render directly" mode for the rest of its
  // life, rather than flip-flopping back to animating if it happened to
  // dip under the threshold on an earlier delta.
  const tooLongRef = useRef(fullText.length > MAX_ANIMATED_LENGTH);
  if (fullText.length > MAX_ANIMATED_LENGTH) tooLongRef.current = true;

  useEffect(() => {
    if (!everEnabledRef.current || tooLongRef.current) {
      setShownLength(fullText.length);
      return;
    }

    let raf = 0;
    let lastTickAt = performance.now();

    const tick = (now: number) => {
      const elapsed = now - lastTickAt;
      const charsToReveal = Math.floor(elapsed / MS_PER_CHAR);

      if (charsToReveal > 0) {
        lastTickAt += charsToReveal * MS_PER_CHAR;
        setShownLength((prev) => Math.min(prev + charsToReveal, fullText.length));
      }

      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => cancelAnimationFrame(raf);
  }, [fullText]);

  return fullText.slice(0, Math.min(shownLength, fullText.length));
}

export function Message({
  message,
  onOpenFile,
  onRunCode,
}: {
  message: ChatMessage;
  onOpenFile?: (file: GeneratedFile) => void;
  onRunCode?: (language: string, code: string) => void;
}) {
  // Only animate while the reply is actually still streaming in — once a
  // turn is done (or for a re-rendered message from earlier in the
  // conversation), show it instantly rather than replaying the typing
  // effect every time this component happens to re-mount.
  const displayedText = useTypewriter(message.text, message.role === "assistant" && !message.streamDone);

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl bg-user-bubble px-4 py-2.5 text-[15px] leading-6 whitespace-pre-wrap">
          {message.text}
        </div>
      </div>
    );
  }

  // Show the typing indicator any time we're still waiting on the reply's
  // own text — whether or not tool calls happened first. Gating this on
  // "no tool calls yet" left a dead gap between the last tool call
  // finishing and the first word of text actually appearing.
  const showTyping = message.pending && !displayedText;
  const isTyping = message.pending && displayedText.length < message.text.length;
  // message.incomplete (see useChat.ts) means the SSE connection ended
  // before a final_response ever arrived — a dropped stream, not a short
  // real answer. It can happen with partial text already on screen (cut
  // off mid-sentence) or with nothing at all.
  const cutOff = !message.pending && message.incomplete;
  // Separately: the turn can also end with a REAL final_response that
  // just happens to carry no text and produced no tool calls/files either
  // — Gemini silently returning nothing, which has shown up in practice
  // (a long/garbled history from earlier broken turns confusing a later
  // round into an empty reply). That's not "incomplete" in the dropped-
  // connection sense, but it's exactly as invisible on screen if nothing
  // is shown for it, so it needs the same visible fallback.
  const finishedEmpty =
    !message.pending && !message.incomplete && !displayedText && message.toolCalls.length === 0 && message.files.length === 0;

  return (
    <div className="flex flex-col gap-2.5">
      {message.toolCalls.length > 0 && (
        <div className="flex flex-col gap-1.5">
          {message.toolCalls.map((call, i) => (
            <div key={`${call.name}-${i}`} className="mads-tool-row-enter">
              <ToolCallRow call={call} />
            </div>
          ))}
        </div>
      )}

      {showTyping ? (
        <TypingIndicator />
      ) : (
        <>
          {displayedText && (
            <div className="max-w-[75ch] text-[15px] leading-6 text-text">
              <MarkdownText text={displayedText} onRunCode={onRunCode} />
              {isTyping && <span className="typing-caret" aria-hidden="true" />}
            </div>
          )}
          {cutOff && (
            <p className="flex items-center gap-1.5 text-[13px] text-text-muted">
              <CutOffIcon />
              {displayedText ? "Response cut off — the connection dropped." : "No reply came back — the connection may have dropped."}{" "}
              Try asking again.
            </p>
          )}
          {finishedEmpty && (
            <p className="flex items-center gap-1.5 text-[13px] text-text-muted">
              <CutOffIcon />
              Mads didn&apos;t return a reply for that one. Try asking again, or start a new chat if it keeps happening.
            </p>
          )}
        </>
      )}

      {message.files.length > 0 && (
        <div className="flex flex-col gap-1.5 sm:max-w-xs">
          {message.files.map((file) => (
            <DownloadChip key={file.path} file={file} onOpen={onOpenFile} />
          ))}
        </div>
      )}
    </div>
  );
}

function MarkdownText({ text, onRunCode }: { text: string; onRunCode?: (language: string, code: string) => void }) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];

    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (line.trim().startsWith("```")) {
      const language = line.trim().slice(3).trim().toLowerCase();
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      const codeText = code.join("\n");
      blocks.push(
        <CodeBlock key={`code-${index}`} language={language} code={codeText} onRunCode={onRunCode} />,
      );
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const className =
        level === 1
          ? "text-xl font-semibold tracking-tight"
          : level === 2
            ? "text-lg font-semibold tracking-tight"
            : "text-base font-semibold";
      blocks.push(
        <div key={`heading-${index}`} className={className}>
          {renderInline(heading[2], `heading-${index}`)}
        </div>,
      );
      index += 1;
      continue;
    }

    const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
    if (unordered) {
      const items: ReactNode[] = [];
      while (index < lines.length) {
        const item = lines[index].match(/^\s*[-*+]\s+(.+)$/);
        if (!item) break;
        items.push(<li key={`bullet-${index}`}>{renderInline(item[1], `bullet-${index}`)}</li>);
        index += 1;
      }
      blocks.push(
        <ul key={`list-${index}`} className="ml-5 list-disc space-y-1.5 marker:text-text-faint">
          {items}
        </ul>,
      );
      continue;
    }

    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (ordered) {
      const items: ReactNode[] = [];
      while (index < lines.length) {
        const item = lines[index].match(/^\s*\d+[.)]\s+(.+)$/);
        if (!item) break;
        items.push(<li key={`number-${index}`}>{renderInline(item[1], `number-${index}`)}</li>);
        index += 1;
      }
      blocks.push(
        <ol key={`ordered-${index}`} className="ml-5 list-decimal space-y-1.5 marker:text-text-muted">
          {items}
        </ol>,
      );
      continue;
    }

    if (line.startsWith("> ")) {
      const quote: string[] = [];
      while (index < lines.length && lines[index].startsWith("> ")) {
        quote.push(lines[index].slice(2));
        index += 1;
      }
      blocks.push(
        <blockquote key={`quote-${index}`} className="border-l-2 border-border-strong pl-4 text-text-muted">
          {renderInline(quote.join(" "), `quote-${index}`)}
        </blockquote>,
      );
      continue;
    }

    // This line reached here precisely because none of the block parsers
    // above matched it — including isBlockStart's own looser checks (e.g.
    // a numbered-list line streamed in up to "1. " with its content not
    // arrived yet: isBlockStart's regex only needs trailing whitespace, so
    // it says yes, but the stricter `(.+)$` ordered-list match above says
    // no). Looping on `!isBlockStart(line)` for even the FIRST line here
    // can then be false immediately — zero lines consumed, `index` never
    // advances, and the outer while loop spins on it forever, hanging the
    // tab. Always consuming this line unconditionally guarantees forward
    // progress regardless of what isBlockStart thinks about it; only
    // lines AFTER the first still defer to it, for normal multi-line
    // paragraph joining.
    const paragraph: string[] = [lines[index].trim()];
    index += 1;
    while (index < lines.length && lines[index].trim() && !isBlockStart(lines[index])) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(
      <p key={`paragraph-${index}`}>{renderInline(paragraph.join(" "), `paragraph-${index}`)}</p>,
    );
  }

  return <div className="space-y-3">{blocks}</div>;
}

function isBlockStart(line: string) {
  return (
    /^#{1,3}\s+/.test(line) ||
    /^\s*[-*+]\s+/.test(line) ||
    /^\s*\d+[.)]\s+/.test(line) ||
    line.startsWith("> ") ||
    line.trim().startsWith("```")
  );
}

// Trailing punctuation a URL often butts up against in prose ("...watch?v=abc.",
// "see https://x.com, then...") isn't part of the link — stripped off here and
// put back as plain text so it doesn't get swallowed into the href.
const URL_TRAILING_PUNCTUATION = /[.,;:!?]+$/;

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const tokenPattern =
    /(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s)]+)/g;
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenPattern.exec(text)) !== null) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index));
    const token = match[0];
    const key = `${keyPrefix}-${match.index}`;

    if (token.startsWith("**")) {
      nodes.push(<strong key={key} className="font-semibold text-text">{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      nodes.push(
        <code key={key} className="rounded bg-code-bg px-1.5 py-0.5 font-mono text-[0.9em]">
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith("[")) {
      const link = token.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
      if (link) {
        nodes.push(
          <a
            key={key}
            href={link[2]}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
          >
            {link[1]}
          </a>,
        );
      }
    } else {
      // A bare URL (no [text](...) wrapper) — e.g. the model just dropped
      // "https://..." straight into its reply instead of markdown-linking it.
      const trailingMatch = token.match(URL_TRAILING_PUNCTUATION);
      const trailing = trailingMatch ? trailingMatch[0] : "";
      const url = trailing ? token.slice(0, -trailing.length) : token;
      nodes.push(
        <a
          key={key}
          href={url}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
        >
          {url}
        </a>,
      );
      if (trailing) nodes.push(trailing);
    }
    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes.map((node, index) => <Fragment key={`${keyPrefix}-part-${index}`}>{node}</Fragment>);
}

/** A fenced code block with a persistent header (language + copy + Run) —
 * always visible, never a hover-only affordance that's easy to miss or
 * clip at the edge of the block. */
function CodeBlock({
  language,
  code,
  onRunCode,
}: {
  language: string;
  code: string;
  onRunCode?: (language: string, code: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  const runnable = onRunCode && RUNNABLE_LANGUAGES.has(language);
  const displayLanguage = language ? language.charAt(0).toUpperCase() + language.slice(1) : "Code";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can be denied/unavailable — not worth surfacing.
    }
  };

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-code-bg">
      <div className="flex items-center justify-between gap-2 border-b border-border px-3.5 py-2">
        <span className="flex items-center gap-1.5 text-[12.5px] font-medium text-text-muted">
          <CodeIcon />
          {displayLanguage}
        </span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={copy}
            aria-label="Copy code"
            title="Copy"
            className="flex h-7 w-7 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-user-bubble hover:text-text"
          >
            {copied ? <CheckIcon /> : <CopyIcon />}
          </button>
          {runnable && (
            <button
              type="button"
              onClick={() => onRunCode(language, code)}
              className="flex items-center gap-1.5 rounded-full border border-border-strong px-3 py-1 text-[12.5px] font-medium text-text transition-colors hover:bg-user-bubble"
            >
              <RunIcon />
              Run
            </button>
          )}
        </div>
      </div>
      <pre className="overflow-x-auto px-4 py-3 font-mono text-[13px] leading-5">
        <code>{code}</code>
      </pre>
    </div>
  );
}

function CutOffIcon() {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" fill="none" className="shrink-0">
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.4" />
      <path d="M8 5v3.5M8 11h.01" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function CodeIcon() {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" fill="none">
      <path d="M5.5 4L2 8l3.5 4M10.5 4L14 8l-3.5 4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" fill="none">
      <rect x="5.5" y="5.5" width="8" height="8" rx="1.3" stroke="currentColor" strokeWidth="1.3" />
      <path d="M3.5 10.5h-1a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v1" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" fill="none">
      <path d="M3.5 8.5l2.5 2.5L12.5 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RunIcon() {
  return (
    <svg viewBox="0 0 16 16" width="11" height="11" fill="none">
      <path d="M5 3.5l7 4.5-7 4.5Z" fill="currentColor" />
    </svg>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 py-1" aria-label="Mads is thinking">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-text-faint [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-text-faint [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-text-faint" />
    </div>
  );
}
