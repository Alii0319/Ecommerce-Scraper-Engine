/**
 * Tests for useWebSocketAlerts hook.
 *
 * Strategy: We spy on the module-level authService and WebSocket constructor,
 * then advance microtasks/timers to drive the async connect() call forward.
 */
import { renderHook, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach, Mock } from 'vitest';

// Mock the api module BEFORE importing the hook
vi.mock('../../services/api', () => ({
  authService: {
    getWsTicket: vi.fn(),
  },
}));

import { useWebSocketAlerts } from '../useWebSocketAlerts';
import { authService } from '../../services/api';

// ---------------------------------------------------------------------------
// MockWebSocket — minimal shim that records instances and exposes callbacks
// ---------------------------------------------------------------------------
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  url: string;
  readyState = 1; // OPEN
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;

  send = vi.fn();
  close = vi.fn(() => {
    this.readyState = 3;
    this.onclose?.({ code: 1000 });
  });

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function latestSocket() {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1];
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------
describe('useWebSocketAlerts', () => {
  let OriginalWebSocket: typeof WebSocket;

  beforeEach(() => {
    vi.clearAllMocks();
    OriginalWebSocket = globalThis.WebSocket;
    (globalThis as unknown as Record<string, unknown>).WebSocket = MockWebSocket;
    MockWebSocket.instances = [];

    // Fake localStorage with a token so the hook decides to connect
    window.localStorage.setItem('access_token', 'fake-access-token');
  });

  afterEach(() => {
    (globalThis as unknown as Record<string, unknown>).WebSocket = OriginalWebSocket;
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  it('ticket fetch success: creates socket with ticket, no JWT in URL', async () => {
    (authService.getWsTicket as Mock).mockResolvedValue({ ticket: 'abc-ticket-123' });

    renderHook(() => useWebSocketAlerts());

    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1), { timeout: 3000 });

    expect(authService.getWsTicket).toHaveBeenCalledOnce();
    expect(MockWebSocket.instances[0].url).toContain('ticket=abc-ticket-123');
    expect(MockWebSocket.instances[0].url).not.toMatch(/token=/i);
  });

  // -------------------------------------------------------------------------
  it('missing stored access token: stays idle and creates no socket', async () => {
    window.localStorage.removeItem('access_token');

    const { result } = renderHook(() => useWebSocketAlerts());

    await waitFor(() => expect(result.current.connectionState).toBe('idle'));
    expect(authService.getWsTicket).not.toHaveBeenCalled();
    expect(MockWebSocket.instances.length).toBe(0);
  });

  // -------------------------------------------------------------------------
  it('ticket fetch failure: no socket created, state becomes error', async () => {
    (authService.getWsTicket as Mock).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useWebSocketAlerts());

    await waitFor(() => expect(result.current.connectionState).toBe('error'), { timeout: 3000 });

    expect(MockWebSocket.instances.length).toBe(0);
  });

  // -------------------------------------------------------------------------
  it('no JWT fallback: connection state becomes error on ticket failure (never idle→connected via token)', async () => {
    (authService.getWsTicket as Mock).mockRejectedValue(new Error('401 Unauthorized'));

    const { result } = renderHook(() => useWebSocketAlerts());

    await waitFor(() => expect(result.current.connectionState).toBe('error'), { timeout: 3000 });

    // Confirm no socket was ever constructed (no JWT fallback path)
    expect(MockWebSocket.instances.length).toBe(0);
  });

  // -------------------------------------------------------------------------
  it('valid v2 event: parsed, added to notifications, ACK sent', async () => {
    (authService.getWsTicket as Mock).mockResolvedValue({ ticket: 'ack-ticket' });

    const { result } = renderHook(() => useWebSocketAlerts());
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1), { timeout: 3000 });

    const ws = latestSocket();

    const validEvent = {
      type: 'price_alert',
      version: 2,
      event_id: 'evt-uuid-001',
      data: {
        product_id: 1,
        history_id: 2,
        product_name: 'Test Product',
        current_price: '1000',
        threshold: '1500',
        target_url: 'https://example.com/p',
        timestamp: '2026-01-01T00:00:00Z',
      },
    };

    act(() => {
      ws.onmessage?.({ data: JSON.stringify(validEvent) });
    });

    expect(result.current.notifications).toHaveLength(1);
    expect(result.current.notifications[0].id).toBe('evt-uuid-001');

    expect(ws.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'alert_ack', version: 1, event_id: 'evt-uuid-001' })
    );
  });

  // -------------------------------------------------------------------------
  it('duplicate event: only one notification, ACK sent once per event', async () => {
    (authService.getWsTicket as Mock).mockResolvedValue({ ticket: 'dedup-ticket' });

    const { result } = renderHook(() => useWebSocketAlerts());
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1), { timeout: 3000 });

    const ws = latestSocket();
    const payload = JSON.stringify({
      type: 'price_alert',
      version: 2,
      event_id: 'dup-001',
      data: {
        product_id: 5,
        history_id: 5,
        product_name: 'Dup Product',
        current_price: '50',
        threshold: '100',
        target_url: 'https://example.com/dup',
        timestamp: '2026-01-01T00:00:00Z',
      },
    });

    act(() => {
      ws.onmessage?.({ data: payload });
      ws.onmessage?.({ data: payload }); // duplicate
    });

    expect(result.current.notifications).toHaveLength(1);
    expect(ws.send).toHaveBeenCalledTimes(2); // ACK sent for each message received
  });

  // -------------------------------------------------------------------------
  it('malformed event: ignored, no notification added', async () => {
    (authService.getWsTicket as Mock).mockResolvedValue({ ticket: 'malform-ticket' });

    const { result } = renderHook(() => useWebSocketAlerts());
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1), { timeout: 3000 });

    const ws = latestSocket();

    act(() => {
      ws.onmessage?.({ data: 'not-valid-json{{{' });
      ws.onmessage?.({ data: JSON.stringify({ type: 'unknown_type', version: 2 }) });
      ws.onmessage?.({ data: JSON.stringify({ type: 'price_alert', version: 2, data: null }) });
    });

    expect(result.current.notifications).toHaveLength(0);
  });

  // -------------------------------------------------------------------------
  it('normal close reconnects with a fresh ticket', async () => {
    (authService.getWsTicket as Mock)
      .mockResolvedValueOnce({ ticket: 'ticket-r1' })
      .mockResolvedValueOnce({ ticket: 'ticket-r2' });

    renderHook(() => useWebSocketAlerts());
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1), { timeout: 3000 });

    const ws1 = MockWebSocket.instances[0];
    expect(ws1.url).toContain('ticket-r1');

    act(() => {
      ws1.readyState = MockWebSocket.CLOSED;
      ws1.onclose?.({ code: 1006 });
    });

    await waitFor(() => expect(MockWebSocket.instances.length).toBe(2), { timeout: 2500 });
    expect(MockWebSocket.instances[1].url).toContain('ticket-r2');
    expect(MockWebSocket.instances[1].url).not.toMatch(/token=/i);
  });

  // -------------------------------------------------------------------------
  it('auth close stops reconnect', async () => {
    (authService.getWsTicket as Mock).mockResolvedValue({ ticket: 'ticket-auth-close' });

    renderHook(() => useWebSocketAlerts());
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1), { timeout: 3000 });

    const ws = MockWebSocket.instances[0];
    act(() => {
      ws.readyState = MockWebSocket.CLOSED;
      ws.onclose?.({ code: 4403 });
    });

    await new Promise((resolve) => setTimeout(resolve, 1200));
    expect(MockWebSocket.instances.length).toBe(1);
  });

  // -------------------------------------------------------------------------
  it('acknowledgeAlert: removes notification from state', async () => {
    (authService.getWsTicket as Mock).mockResolvedValue({ ticket: 'ack-rem-ticket' });

    const { result } = renderHook(() => useWebSocketAlerts());
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1), { timeout: 3000 });

    const ws = latestSocket();

    act(() => {
      ws.onmessage?.({
        data: JSON.stringify({
          type: 'price_alert',
          version: 2,
          event_id: 'remove-me',
          data: {
            product_id: 9,
            history_id: 9,
            product_name: 'Remove Me',
            current_price: '200',
            threshold: '300',
            target_url: 'https://example.com',
            timestamp: '2026-01-01T00:00:00Z',
          },
        }),
      });
    });

    expect(result.current.notifications).toHaveLength(1);

    act(() => { result.current.acknowledgeAlert('remove-me'); });

    expect(result.current.notifications).toHaveLength(0);
  });
});
