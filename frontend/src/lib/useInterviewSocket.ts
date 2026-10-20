"use client";

import { useEffect, useRef, useState } from "react";
import { getAccessToken, refreshAccess, wsUrl } from "./api";
import type { WsEvent } from "./types";

/**
 * Authenticated WebSocket for a session. Reconnects with backoff; on reconnect the server sends a fresh
 * snapshot, which is how the UI recovers after network or browser interruptions.
 */
export function useInterviewSocket(sessionId: string | null, role: "candidate" | "monitor", onEvent: (e: WsEvent) => void) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    if (!sessionId) return;
    let closed = false;
    let attempt = 0;
    let ping: ReturnType<typeof setInterval> | undefined;

    const connect = async () => {
      if (!getAccessToken()) await refreshAccess();
      const ws = new WebSocket(wsUrl(`/ws/interview/${sessionId}`));
      wsRef.current = ws;
      ws.onopen = () => {
        ws.send(JSON.stringify({ type: "auth", token: getAccessToken(), role }));
        attempt = 0;
        setConnected(true);
        ping = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ type: "ping" })), 25_000);
      };
      ws.onmessage = (m) => {
        try {
          const ev = JSON.parse(m.data) as WsEvent;
          if (ev.type !== "pong") handler.current(ev);
        } catch { /* ignore malformed */ }
      };
      ws.onclose = async (ev) => {
        setConnected(false);
        clearInterval(ping);
        if (closed) return;
        if (ev.code === 4401) await refreshAccess();
        attempt += 1;
        setTimeout(connect, Math.min(1000 * 2 ** attempt, 15_000));
      };
    };
    connect();
    return () => {
      closed = true;
      clearInterval(ping);
      wsRef.current?.close();
    };
  }, [sessionId, role]);

  const send = (type: string, data: unknown) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type, data }));
  };
  return { connected, send };
}
