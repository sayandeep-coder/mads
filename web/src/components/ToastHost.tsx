"use client";

import { useEffect, useRef, useState } from "react";
import { subscribeToast } from "@/lib/toast";

interface ToastItem {
  id: number;
  message: string;
}

let nextId = 1;

export function ToastHost() {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    return subscribeToast((message) => {
      const id = nextId++;
      setItems((prev) => [...prev, { id, message }]);
      const timer = setTimeout(() => {
        setItems((prev) => prev.filter((item) => item.id !== id));
        timersRef.current.delete(id);
      }, 3200);
      timersRef.current.set(id, timer);
    });
  }, []);

  useEffect(() => {
    const timers = timersRef.current;
    return () => timers.forEach((timer) => clearTimeout(timer));
  }, []);

  if (items.length === 0) return null;

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-20 z-[100] flex flex-col items-center gap-2 sm:bottom-6">
      {items.map((item) => (
        <div
          key={item.id}
          className="pointer-events-auto rounded-full border border-border-strong bg-surface-raised px-4 py-2 text-[13px] font-medium text-text shadow-lg"
        >
          {item.message}
        </div>
      ))}
    </div>
  );
}
