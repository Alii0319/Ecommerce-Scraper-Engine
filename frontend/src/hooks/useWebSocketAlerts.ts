import { useCallback, useEffect, useRef, useState } from 'react';

export interface AlertItem {
  id: string;
  productName: string;
  currentPrice: number;
  timestamp: string;
}

interface UseWebSocketAlertsResult {
  notifications: AlertItem[];
  connectionState: 'connecting' | 'connected' | 'error' | 'disconnected';
  acknowledgeAlert: (id: string) => void;
  setNotificationCallback: (callback: (alert: AlertItem) => void) => void;
  triggerLocalAlert: (alert: Omit<AlertItem, 'id'>) => void;
}

const getAccessToken = (): string | null => {
  if (typeof window === 'undefined') {
    return null;
  }

  return window.localStorage.getItem('access_token');
};

export const useWebSocketAlerts = (): UseWebSocketAlertsResult => {
  const [notifications, setNotifications] = useState<AlertItem[]>([]);
  const [connectionState, setConnectionState] = useState<'connecting' | 'connected' | 'error' | 'disconnected'>('disconnected');
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const reconnectTimerRef = useRef<number | null>(null);
  const callbackRef = useRef<((alert: AlertItem) => void) | null>(null);

  const acknowledgeAlert = useCallback((id: string) => {
    setNotifications((current) => current.filter((alert) => alert.id !== id));
  }, []);

  const notifyBrowser = useCallback((alert: AlertItem) => {
    if (typeof window === 'undefined' || typeof Notification === 'undefined') {
      return;
    }

    if (Notification.permission === 'default') {
      void Notification.requestPermission();
    }

    if (Notification.permission === 'granted') {
      new Notification('Price threshold alert', {
        body: `${alert.productName} now at Rs. ${alert.currentPrice} (${alert.timestamp})`,
      });
    }
  }, []);

  const triggerLocalAlert = useCallback((alert: Omit<AlertItem, 'id'>) => {
    const newAlert: AlertItem = {
      ...alert,
      id: `${alert.productName}-${alert.timestamp}-${Date.now()}-${Math.random()}`,
    };
    setNotifications((current) => [newAlert, ...current].slice(0, 5));
    notifyBrowser(newAlert);
  }, [notifyBrowser]);

  const connect = useCallback(() => {
    const token = getAccessToken();
    if (!token) {
      setConnectionState('error');
      return;
    }

    const ws = new WebSocket(`ws://localhost:8000/ws/alerts/?token=${encodeURIComponent(token)}`);
    socketRef.current = ws;
    setConnectionState('connecting');

    ws.onopen = () => {
      reconnectAttemptsRef.current = 0;
      setConnectionState('connected');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'price_threshold_alert') {
          const alert: AlertItem = {
            id: data.id || `${data.product_name || 'product'}-${data.timestamp || Date.now()}-${Math.random()}`,
            productName: data.product_name || 'Product',
            currentPrice: parseFloat(String(data.current_price)) || 0,
            timestamp: data.timestamp || new Date().toLocaleTimeString(),
          };
          setNotifications((current) => [alert, ...current].slice(0, 5));
          callbackRef.current?.(alert);
          notifyBrowser(alert);
        }
      } catch (err) {
        // Safe catch
      }
    };

    ws.onerror = () => {
      setConnectionState('error');
    };

    ws.onclose = () => {
      setConnectionState('disconnected');
      const attempts = reconnectAttemptsRef.current + 1;
      reconnectAttemptsRef.current = attempts;
      const delay = Math.min(5000 * attempts, 30000);

      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
      }

      reconnectTimerRef.current = window.setTimeout(() => {
        connect();
      }, delay);
    };
  }, [notifyBrowser]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
      }

      socketRef.current?.close();
    };
  }, [connect]);

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
};
