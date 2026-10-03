"use client";

/**
 * Minimal toast pub/sub — no provider/context needed. `toast()` can be
 * called from anywhere (event handlers, hooks); `ToastHost` (rendered once
 * near the app root) is the only subscriber that actually renders anything.
 */
type Listener = (message: string) => void;
const listeners = new Set<Listener>();

export function toast(message: string) {
  listeners.forEach((listener) => listener(message));
}

export function subscribeToast(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
