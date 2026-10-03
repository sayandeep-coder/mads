"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMode } from "@/components/ChatInput";
import type { AgentEvent, ChatMessage, GeneratedFile, ToolCallState } from "./types";

const FILE_KIND_BY_EXTENSION: Record<string, GeneratedFile["kind"]> = {
  pdf: "pdf",
  pptx: "pptx",
  xlsx: "xlsx",
  png: "image",
  jpg: "image",
  jpeg: "image",
  webp: "image",
};

function inferFileKind(name: string): GeneratedFile["kind"] {
  const extension = name.split(".").pop()?.toLowerCase() ?? "";
  return FILE_KIND_BY_EXTENSION[extension] ?? "file";
}

/** Pulls a generated-file attachment out of a tool result, if it looks
 * like one (create_pdf/create_presentation/image tools all return a
 * "path" key — see agent.agent._parse_tool_output for how it gets here). */
function extractGeneratedFile(result: Record<string, unknown> | undefined): GeneratedFile | null {
  const path = result?.path;
  if (typeof path !== "string" || !path) return null;

  const name = path.split("/").pop() || path;
  return { path, name, kind: inferFileKind(name) };
}

export const API_BASE =
  typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "";

let nextId = 1;
function makeId(): string {
  return `msg-${nextId++}-${Date.now()}`;
}

interface StoredMessage {
  id: number;
  role: "user" | "model";
  text: string;
  tool_calls: { name: string; args?: Record<string, unknown> }[];
  files: { path: string; name: string }[];
}

function fromStoredMessage(row: StoredMessage): ChatMessage {
  return {
    id: `stored-${row.id}`,
    role: row.role === "model" ? "assistant" : "user",
    text: row.text,
    fullText: row.text,
    streamDone: true,
    pending: false,
    toolCalls: row.tool_calls.map((tc) => ({ name: tc.name, args: tc.args, status: "done" as const })),
    files: row.files.map((f) => ({ path: f.path, name: f.name, kind: inferFileKind(f.name) })),
  };
}

/**
 * Consumes the backend's POST /api/chat SSE stream. EventSource only
 * supports GET, so this parses the `event:`/`data:` line protocol by hand
 * over a fetch() ReadableStream — same wire format, just read manually.
 *
 * Each conversation is a stored session (ChatStore, server-side); this hook
 * is handed `sessionId` by the page (which owns the sidebar's active
 * selection) and reloads that session's history whenever it changes —
 * except for the one change it causes itself, when the backend hands back
 * a freshly-created session_id for a message sent with none yet (see
 * skipNextLoadRef below).
 */
export function useChat(sessionId: string | null, onSessionCreated: (id: string) => void) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const requestVersionRef = useRef(0);
  const skipNextLoadRef = useRef(false);

  useEffect(() => {
    if (skipNextLoadRef.current) {
      skipNextLoadRef.current = false;
      return;
    }
    if (!sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`);
        if (!res.ok) throw new Error(`Server responded ${res.status}`);
        const data = (await res.json()) as { messages: StoredMessage[] };
        if (cancelled) return;
        setMessages(data.messages.map(fromStoredMessage));
      } catch {
        if (!cancelled) setMessages([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const sendMessage = useCallback(async (text: string, file?: File, mode?: ChatMode) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const requestVersion = ++requestVersionRef.current;

    setError(null);

    const userMessage: ChatMessage = {
      id: makeId(),
      role: "user",
      text: file ? `${trimmed}\nAttached: ${file.name}` : trimmed,
      fullText: "",
      streamDone: true,
      toolCalls: [],
      pending: false,
      files: [],
    };
    const assistantId = makeId();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      text: "",
      fullText: "",
      streamDone: false,
      toolCalls: [],
      pending: true,
      files: [],
    };

    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    const applyEvent = (event: AgentEvent) => {
      if (requestVersion !== requestVersionRef.current) return;

      if (event.type === "session_created" && event.session_id) {
        skipNextLoadRef.current = true;
        onSessionCreated(event.session_id);
        return;
      }

      setMessages((prev) =>
        prev.map((m) => {
          if (m.id !== assistantId) return m;

          if (event.type === "tool_call_started" && event.tool_name) {
            const call: ToolCallState = {
              name: event.tool_name,
              args: event.tool_args,
              status: "running",
              callId: event.call_id,
            };
            return { ...m, toolCalls: [...m.toolCalls, call] };
          }

          if (event.type === "tool_call_output" && event.call_id) {
            // Live stdout/stderr chunk from a running shell command —
            // append it to that call's buffer so ToolCallRow can render it
            // as a growing terminal block while the command is still going.
            const toolCalls = m.toolCalls.map((tc) =>
              tc.callId === event.call_id
                ? { ...tc, terminalOutput: (tc.terminalOutput ?? "") + (event.output ?? "") }
                : tc
            );
            return { ...m, toolCalls };
          }

          if (event.type === "tool_call_finished" && event.tool_name) {
            // Prefer matching the exact call via call_id (always set for
            // live events); fall back to the oldest still-running call with
            // this name, since tool names can repeat in one turn (e.g. two
            // file reads) and older/replayed data may lack a call_id.
            let matched = false;
            const toolCalls = m.toolCalls.map((tc) => {
              if (matched || tc.status !== "running") return tc;
              const isMatch = event.call_id ? tc.callId === event.call_id : tc.name === event.tool_name;
              if (!isMatch) return tc;
              matched = true;
              return { ...tc, status: event.is_error ? "error" : "done" } as ToolCallState;
            });

            const generatedFile = event.is_error ? null : extractGeneratedFile(event.result);
            const files = generatedFile ? [...m.files, generatedFile] : m.files;

            return { ...m, toolCalls, files };
          }

          if (event.type === "text_delta") {
            const nextFullText = m.fullText + (event.text ?? "");
            return { ...m, fullText: nextFullText, text: nextFullText };
          }

          if (event.type === "final_response") {
            const nextFullText = m.fullText || event.text || "";
            return { ...m, fullText: nextFullText, text: nextFullText, streamDone: true, pending: false };
          }

          return m;
        })
      );
    };

    try {
      // Scoped to this one call, not a persistent ref — an attachment
      // should only ever apply to the message it was actually sent with,
      // never silently stick around and get re-appended to every later,
      // unrelated message in the conversation.
      let uploadedPath: string | null = null;
      if (file) {
        const formData = new FormData();
        formData.append("file", file);
        const uploadRes = await fetch(`${API_BASE}/api/upload`, {
          method: "POST",
          body: formData,
          signal: controller.signal,
        });

        if (!uploadRes.ok) throw new Error("File upload failed");
        const uploadData = await uploadRes.json();

        if (requestVersion !== requestVersionRef.current) return;
        uploadedPath = uploadData.path;
      }

      const payloadText = uploadedPath ? `${trimmed}\n\n[Attached File: ${uploadedPath}]` : trimmed;

      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: payloadText, session_id: sessionId, mode: mode ?? null }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        throw new Error(`Server responded ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        // sse-starlette sends CRLF line endings; normalize to LF so the
        // frame/line splitting below doesn't have to special-case \r
        // (a raw "\n\n" split misses "\r\n\r\n" boundaries entirely).
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

        // SSE frames are separated by a blank line; each frame is one or
        // more "field: value" lines. We only care about "data:".
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";

        for (const frame of frames) {
          const dataLine = frame
            .split("\n")
            .find((line) => line.startsWith("data:"));
          if (!dataLine) continue;
          const json = dataLine.slice("data:".length).trim();
          if (!json) continue;
          try {
            applyEvent(JSON.parse(json) as AgentEvent);
          } catch {
            // Malformed frame — skip it rather than break the whole stream.
          }
        }
      }
    } catch (err) {
      if (requestVersion !== requestVersionRef.current) return;
      if ((err as Error).name !== "AbortError") {
        setError(err instanceof Error ? err.message : "Something went wrong.");
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, pending: false, toolCalls: m.toolCalls.map(tc => tc.status === "running" ? { ...tc, status: "error" } : tc) } : m))
        );
      }
    } finally {
      if (requestVersion === requestVersionRef.current) {
        setMessages(prev => prev.map(m => m.id === assistantId && m.pending ? { ...m, pending: false, streamDone: true } : m));
        setIsStreaming(false);
        abortRef.current = null;
      }
    }
  }, [sessionId, onSessionCreated]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const clearMessages = useCallback(() => setMessages([]), []);

  return { messages, sendMessage, isStreaming, error, stop, clearMessages };
}
