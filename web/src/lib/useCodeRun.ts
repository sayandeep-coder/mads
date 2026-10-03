"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const WS_BASE =
  typeof window !== "undefined" ? `ws://${window.location.hostname}:8000` : "";

type RunStatus = "idle" | "running" | "exited" | "error";

/** Drives the user-triggered "Run" button on a code block — a full-duplex
 * WebSocket to /ws/run (server/code_runner.py), completely separate from
 * the agent's own run_command tool. One connection per run; starting a new
 * run while one is live closes the old socket first. */
export function useCodeRun() {
  const wsRef = useRef<WebSocket | null>(null);
  const [output, setOutput] = useState("");
  const [status, setStatus] = useState<RunStatus>("idle");
  const [exitCode, setExitCode] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const start = useCallback((language: string, code: string) => {
    wsRef.current?.close();

    setOutput("");
    setExitCode(null);
    setErrorMessage(null);
    setStatus("running");

    const ws = new WebSocket(`${WS_BASE}/ws/run`);
    wsRef.current = ws;

    // Every handler below checks `wsRef.current === ws` before touching
    // state — without it, a late event from a socket `start()` already
    // superseded (e.g. React Strict Mode's deliberate mount->cleanup->
    // mount in dev, or the user clicking Run again quickly) can land after
    // the NEW run is already live and stomp its status with a stale
    // "closed"/"errored" from the connection nothing is using anymore.
    const isCurrent = () => wsRef.current === ws;

    ws.onopen = () => {
      if (isCurrent()) ws.send(JSON.stringify({ action: "start", language, code }));
    };

    ws.onmessage = (event) => {
      if (!isCurrent()) return;
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "output") {
          setOutput((prev) => prev + msg.text);
        } else if (msg.type === "exit") {
          setStatus("exited");
          setExitCode(msg.code);
        } else if (msg.type === "error") {
          setStatus("error");
          setErrorMessage(msg.message);
        }
      } catch {
        // Malformed frame — ignore rather than crash the run view.
      }
    };

    ws.onerror = () => {
      if (isCurrent()) setStatus((prev) => (prev === "running" ? "error" : prev));
    };
    ws.onclose = () => {
      if (isCurrent()) setStatus((prev) => (prev === "running" ? "exited" : prev));
    };
  }, []);

  const sendInput = useCallback((text: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      // Echo the typed line into the output stream ourselves — a real
      // terminal shows your keystrokes inline as you type, so without this
      // the process's prompt (sent with no trailing newline, so the user
      // can type right after it) and whatever the process prints next run
      // together on one line with no visible record of what was typed.
      setOutput((prev) => prev + text + "\n");
      wsRef.current.send(JSON.stringify({ action: "input", text }));
    }
  }, []);

  const stop = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: "stop" }));
    }
  }, []);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  return { output, status, exitCode, errorMessage, start, sendInput, stop };
}
