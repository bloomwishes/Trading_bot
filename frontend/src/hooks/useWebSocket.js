import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * Custom hook for WebSocket connections with auto-reconnect
 * @param {string} url - WebSocket URL path (e.g., '/ws/logs')
 * @returns {{ data: any, messages: any[], isConnected: boolean, error: string|null, send: function }}
 */
export default function useWebSocket(url) {
  const [data, setData] = useState(null);
  const [messages, setMessages] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttemptRef = useRef(0);
  const maxReconnectAttempts = 20;
  const mountedRef = useRef(true);

  const getReconnectDelay = useCallback((attempt) => {
    // Exponential backoff: 1s, 2s, 4s, 8s, max 30s
    return Math.min(1000 * Math.pow(2, attempt), 30000);
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    try {
      // Build full WebSocket URL
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const fullUrl = `${protocol}//${host}${url}`;

      const ws = new WebSocket(fullUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setIsConnected(true);
        setError(null);
        reconnectAttemptRef.current = 0;
        console.log(`[WS] Connected to ${url}`);
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const parsed = JSON.parse(event.data);
          setData(parsed);
          setMessages((prev) => {
            const updated = [...prev, parsed];
            // Keep max 500 messages
            if (updated.length > 500) {
              return updated.slice(updated.length - 500);
            }
            return updated;
          });
        } catch {
          // Not JSON, store raw
          setData(event.data);
          setMessages((prev) => {
            const updated = [...prev, event.data];
            if (updated.length > 500) {
              return updated.slice(updated.length - 500);
            }
            return updated;
          });
        }
      };

      ws.onerror = (event) => {
        if (!mountedRef.current) return;
        console.error(`[WS] Error on ${url}:`, event);
        setError('WebSocket connection error');
      };

      ws.onclose = (event) => {
        if (!mountedRef.current) return;
        setIsConnected(false);
        console.log(`[WS] Disconnected from ${url}, code: ${event.code}`);

        // Auto-reconnect
        if (reconnectAttemptRef.current < maxReconnectAttempts) {
          const delay = getReconnectDelay(reconnectAttemptRef.current);
          console.log(`[WS] Reconnecting in ${delay}ms (attempt ${reconnectAttemptRef.current + 1})`);
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptRef.current += 1;
            connect();
          }, delay);
        } else {
          setError('Max reconnection attempts reached');
        }
      };
    } catch (err) {
      console.error(`[WS] Failed to create WebSocket:`, err);
      setError(err.message);
    }
  }, [url, getReconnectDelay]);

  const send = useCallback((data) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data));
    }
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounting');
      }
    };
  }, [connect]);

  return { data, messages, isConnected, error, send, clearMessages };
}
