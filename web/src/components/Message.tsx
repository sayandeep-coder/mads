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
}: {
  message: ChatMessage;
  onOpenFile?: (file: GeneratedFile) => void;
}) {
  // Only animate while the reply is actually still streaming in — once a
  // turn is done (or for a re-rendered message from earlier in the
  // conversation), show it instantly rather than replaying the typing
  // effect every time this component happens to re-mount.
  const displayedText = useTypewriter(message.text, message.role === "assistant" && !message.streamDone);

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl bg-user-bubble px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap">
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

  return (
    <div className="flex flex-col gap-2.5">
      {message.toolCalls.length > 0 && (
        <div className="flex flex-col gap-1.5">
          {message.toolCalls.map((call, i) => (
            <ToolCallRow key={`${call.name}-${i}`} call={call} />
          ))}
        </div>
      )}

      {showTyping ? (
        <TypingIndicator />
      ) : (
        displayedText && (
          <div className="max-w-[75ch] text-[15px] leading-relaxed text-text">
            <MarkdownText text={displayedText} />
            {isTyping && <span className="typing-caret" aria-hidden="true" />}
          </div>
        )
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

function MarkdownText({ text }: { text: string }) {
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
      const language = line.trim().slice(3);
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push(
        <pre
          key={`code-${index}`}
          className="overflow-x-auto rounded-xl bg-code-bg px-4 py-3 font-mono text-[13px] leading-5"
          data-language={language || undefined}
        >
          <code>{code.join("\n")}</code>
        </pre>,
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

    const paragraph: string[] = [];
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

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const tokenPattern = /(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g;
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
    } else {
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
    }
    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes.map((node, index) => <Fragment key={`${keyPrefix}-part-${index}`}>{node}</Fragment>);
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
