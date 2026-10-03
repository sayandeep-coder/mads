export type AgentEventType =
  | "session_created"
  | "tool_call_started"
  | "tool_call_output"
  | "tool_call_finished"
  | "text_delta"
  | "final_response";

export interface AgentEvent {
  type: AgentEventType;
  session_id?: string;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  is_error?: boolean;
  text?: string;
  result?: Record<string, unknown>;
  /** Identifies which call a started/output/finished event belongs to — only
   * set once a tool call can stream more than one event (run_command). */
  call_id?: string;
  /** One chunk of live output, only set on tool_call_output. */
  output?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  preview?: string | null;
}

export interface ToolCallState {
  name: string;
  args?: Record<string, unknown>;
  status: "running" | "done" | "error";
  /** Correlates started/output/finished events for this call — only
   * present for calls that can stream live output (run_command). */
  callId?: string;
  /** Live-streamed stdout/stderr, accumulated chunk by chunk as it arrives
   * — rendered as a terminal block while the call is running or once done. */
  terminalOutput?: string;
}

export interface GeneratedFile {
  path: string;
  name: string;
  kind: "pdf" | "pptx" | "xlsx" | "image" | "file";
}

/** A user-triggered "Run" on a code block — `id` just needs to change for
 * re-running the same code to restart cleanly (see useCodeRun's `start`). */
export interface CodeRunTarget {
  kind: "code";
  language: string;
  code: string;
  id: number;
}

/** Which generated file or live code run (if any) the split-pane preview panel is currently showing. */
export type PreviewTarget = GeneratedFile | CodeRunTarget | null;

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  /** What's actually painted — revealed character-by-character from fullText by the typewriter loop, never write to this directly. */
  text: string;
  /** Everything received from the backend so far, not yet revealed on screen. */
  fullText: string;
  /** True once the network stream itself has ended (Agent's final_response arrived) — the typewriter loop keeps draining fullText until text catches up even after this flips true. */
  streamDone: boolean;
  toolCalls: ToolCallState[];
  /** True while the assistant turn is still streaming (tool calls and/or text not finished). */
  pending: boolean;
  files: GeneratedFile[];
}
