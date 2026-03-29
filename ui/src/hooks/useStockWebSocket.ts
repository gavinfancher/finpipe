import { useEffect, useRef, useState, useCallback } from "react";
import type { StockTick, ServerMessage } from "../types";

const RECONNECT_DELAY_MS = 3000;

export type ConnectionStatus = "connecting" | "connected" | "disconnected";

export function useStockWebSocket(token: string) {
  const [ticks, setTicks] = useState<Record<string, StockTick>>({});
  const [availableTickers, setAvailableTickers] = useState<string[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmounted = useRef(false);

  const connect = useCallback(() => {
    if (unmounted.current) return;
    setStatus("connecting");

    const ws = new WebSocket(`ws://${window.location.hostname}:8080/ws?token=${token}`);
    wsRef.current = ws;

    ws.onopen = () => {
      if (unmounted.current) return;
      setStatus("connected");
    };

    ws.onmessage = (event: MessageEvent<string>) => {
      if (unmounted.current) return;
      setStatus("connected");
      try {
        const msg: ServerMessage = JSON.parse(event.data);
        if (msg.type === "snapshot") {
          setTicks(msg.ticks);
        } else if (msg.type === "tickers") {
          setAvailableTickers(msg.tickers);
        } else if (msg.type === "tick") {
          setTicks((prev) => ({ ...prev, [msg.tick.ticker]: msg.tick }));
        }
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = () => {
      if (unmounted.current) return;
      setStatus("disconnected");
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [token]);

  useEffect(() => {
    unmounted.current = false;
    connect();
    return () => {
      unmounted.current = true;
      wsRef.current?.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
  }, [connect]);

  return { ticks, availableTickers, status };
}
