import type { ChatMessage } from "@/lib/types";
import { Fragment, type ReactNode } from "react";
import { DownloadChip } from "./DownloadChip";
import { ToolCallRow } from "./ToolCallRow";

export function Message({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl bg-user-bubble px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap">
          {message.text}
        </div>
      </div>
    );
  }

  const showTyping = message.pending && message.toolCalls.length === 0 && !message.text;

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
        message.text && (
          <div className="max-w-[75ch] text-[15px] leading-relaxed text-text">
            <MarkdownText text={message.text} />
          </div>
        )
      )}

      {message.files.length > 0 && (
        <div className="flex flex-col gap-1.5 sm:max-w-xs">
          {message.files.map((file) => (
            <DownloadChip key={file.path} file={file} />
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
