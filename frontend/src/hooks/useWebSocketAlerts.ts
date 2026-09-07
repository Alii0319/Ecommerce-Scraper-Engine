import { useCallback, useEffect, useRef, useState } from "react";
import { authService } from "../services/api";

export interface AlertPayload {
  alert_type?: string;
  product_id: number;
  history_id: number;
  product_name: string;
  current_price: string;
  threshold: string;
  target_url: string;
  timestamp: string;
}

export interface AlertEvent {
  type: "price_alert" | "price_threshold_alert";
  version: 1 | 2;
  event_id?: string;
  data: AlertPayload;
}

export interface AlertItem {
  id: string;
  productId?: number;
  historyId?: number;
  productName: string;
  currentPrice: number;
  threshold?: number;
  targetUrl?: string;
  timestamp: string;
}

export type ConnectionState =
  | "idle"
  | "connecting"
  | "connected"
  | "disconnected"
  | "error";

interface UseWebSocketAlertsResult {
  notifications: AlertItem[];
  connectionState: ConnectionState;
  acknowledgeAlert: (id: string) => void;
  setNotificationCallback: (callback: (alert: AlertItem) => void) => void;
  triggerLocalAlert: (alert: Omit<AlertItem, "id">) => void;
}

const MAX_RECONNECT_DELAY_MS = 30_000;

function getWebSocketBaseUrl(): string {
  const configured = import.meta.env.VITE_WS_BASE_URL?.trim();
  if (configured && (configured.startsWith("ws://") || configured.startsWith("wss://"))) {
    return configured.replace(/\/+$/, "");
  }

  if (typeof window === "undefined") return "ws://localhost:8000";

  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}`;
}

function getStoredAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("access_token");
}

function isAlertEvent(value: unknown): value is AlertEvent {
  if (!value || typeof value !== "object") return false;

  const event = value as Partial<AlertEvent>;
  const data = event.data as Partial<AlertPayload> | undefined;

  return (
    (event.type === "price_alert" || event.type === "price_threshold_alert") &&
    (event.version === 1 || event.version === 2) &&
    !!data &&
    typeof data.product_id === "number" &&
    typeof data.history_id === "number" &&
    typeof data.product_name === "string" &&
    typeof data.current_price === "string" &&
    typeof data.threshold === "string" &&
    typeof data.target_url === "string" &&
    typeof data.timestamp === "string"
  );
}

export function useWebSocketAlerts(): UseWebSocketAlertsResult {
  const [notifications, setNotifications] = useState<AlertItem[]>([]);
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef(0);
  const shouldReconnectRef = useRef(false);
  const callbackRef = useRef<((alert: AlertItem) => void) | null>(null);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const acknowledgeAlert = useCallback((id: string) => {
    setNotifications((current) => current.filter((item) => item.id !== id));
  }, []);

  const notifyBrowser = useCallback((alert: AlertItem) => {
    if (typeof window === "undefined" || typeof Notification === "undefined") return;

    if (Notification.permission === "granted") {
      new Notification("Price threshold reached", {
        body: `${alert.productName}: Rs. ${alert.currentPrice}`,
      });
    }
  }, []);

  const addAlertFromEvent = useCallback(
    (event: AlertEvent) => {
      const payload = event.data;
      const alertId = event.event_id || String(payload.history_id);
      const alert: AlertItem = {
        id: alertId,
        productId: payload.product_id,
        historyId: payload.history_id,
        productName: payload.product_name,
        currentPrice: Number(payload.current_price) || 0,
        threshold: Number(payload.threshold) || 0,
        targetUrl: payload.target_url,
        timestamp: payload.timestamp,
      };

      setNotifications((current) => {
        if (current.some((item) => item.id === alert.id)) return current;
        return [alert, ...current].slice(0, 50);
      });

      // Send ACK back to the server
      if (socketRef.current?.readyState === WebSocket.OPEN && alertId) {
        socketRef.current.send(
          JSON.stringify({
            type: "alert_ack",
            version: 1,
            event_id: alertId,
          })
        );
      }

      callbackRef.current?.(alert);
      notifyBrowser(alert);
    },
    [notifyBrowser]
  );

  const triggerLocalAlert = useCallback(
    (alert: Omit<AlertItem, "id">) => {
      const newAlert: AlertItem = {
        ...alert,
        id: `${alert.productName}-${alert.timestamp}-${Date.now()}-${Math.random()}`,
      };
      setNotifications((current) => [newAlert, ...current].slice(0, 50));
      notifyBrowser(newAlert);
    },
    [notifyBrowser]
  );

  const connect = useCallback(async () => {
    const token = getStoredAccessToken();

    if (!token || !shouldReconnectRef.current) {
      setConnectionState("idle");
      return;
    }

    if (
      socketRef.current?.readyState === WebSocket.OPEN ||
      socketRef.current?.readyState === WebSocket.CONNECTING
    ) {
      return;
    }

    setConnectionState("connecting");

    let ticketStr = "";
    try {
      const ticketRes = await authService.getWsTicket();
      ticketStr = ticketRes.ticket;
    } catch {
      setConnectionState("error");

      reconnectAttemptRef.current += 1;
      const delay = Math.min(
        1_000 * 2 ** (reconnectAttemptRef.current - 1),
        MAX_RECONNECT_DELAY_MS
      );
      clearReconnectTimer();
      reconnectTimerRef.current = window.setTimeout(connect, delay);
      return;
    }

    const url = `${getWebSocketBaseUrl()}/ws/alerts/?ticket=${encodeURIComponent(ticketStr)}`;

    const socket = new WebSocket(url);
    socketRef.current = socket;

    socket.onopen = () => {
      reconnectAttemptRef.current = 0;
      setConnectionState("connected");
    };

    socket.onmessage = (message) => {
      try {
        const parsed: unknown = JSON.parse(message.data);
        if (isAlertEvent(parsed)) {
          addAlertFromEvent(parsed);
        }
      } catch {
        // Ignore malformed external frames.
      }
    };

    socket.onerror = () => setConnectionState("error");

    socket.onclose = (event) => {
      socketRef.current = null;
      setConnectionState("disconnected");

      if (!shouldReconnectRef.current) return;
      if (event.code === 4401 || event.code === 4403) {
        shouldReconnectRef.current = false;
        return;
      }

      reconnectAttemptRef.current += 1;
      const delay = Math.min(
        1_000 * 2 ** (reconnectAttemptRef.current - 1),
        MAX_RECONNECT_DELAY_MS
      );

      clearReconnectTimer();
      reconnectTimerRef.current = window.setTimeout(connect, delay);
    };
  }, [addAlertFromEvent, clearReconnectTimer]);

  useEffect(() => {
    clearReconnectTimer();
    socketRef.current?.close();
    socketRef.current = null;

    const token = getStoredAccessToken();

    if (!token) {
      shouldReconnectRef.current = false;
      setConnectionState("idle");
      return;
    }

    shouldReconnectRef.current = true;
    connect();

    return () => {
      shouldReconnectRef.current = false;
      clearReconnectTimer();
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [connect, clearReconnectTimer]);

  const setNotificationCallback = useCallback((callback: (alert: AlertItem) => void) => {
    callbackRef.current = callback;
  }, []);

  return {
    notifications,
    connectionState,
    acknowledgeAlert,
    setNotificationCallback,
    triggerLocalAlert,
  };
}
