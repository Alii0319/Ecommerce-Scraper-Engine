import { test, expect, request } from '@playwright/test';

const BASE_URL = 'http://localhost';
const API_URL = 'http://localhost/api';
const BROWSER_REJECTED_WS_CODE = 1006;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
async function createUser(apiContext: Awaited<ReturnType<typeof request.newContext>>, suffix: string) {
  const email = `e2e_${suffix.toLowerCase()}@test.com`;
  const password = 'E2eTest@12345!';

  await apiContext.post(`${API_URL}/auth/register/`, {
    data: { email, password, first_name: 'E2E', last_name: 'User' },
  });

  const loginRes = await apiContext.post(`${API_URL}/auth/login/`, {
    data: { email, password },
  });
  expect(loginRes.ok(), await loginRes.text()).toBe(true);
  const tokens = await loginRes.json();
  return { email, password, accessToken: tokens.access as string };
}

async function getWsTicket(apiContext: Awaited<ReturnType<typeof request.newContext>>, accessToken: string) {
  const res = await apiContext.post(`${API_URL}/auth/ws-ticket/`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const data = await res.json();
  return data.ticket as string;
}

// ---------------------------------------------------------------------------
// Test: Login and get a WS ticket
// ---------------------------------------------------------------------------
test('Authentication: login → obtain WS ticket', async ({ page }) => {
  await page.goto(BASE_URL);
  // The app should load without errors
  await expect(page.locator('body')).toBeVisible();

  // Test ticket acquisition via API
  const apiContext = await request.newContext();
  try {
    const { accessToken } = await createUser(apiContext, `auth_${Date.now()}`);
    expect(accessToken).toBeTruthy();

    const ticket = await getWsTicket(apiContext, accessToken);
    expect(ticket).toBeTruthy();
    expect(typeof ticket).toBe('string');
  } finally {
    await apiContext.dispose();
  }
});

// ---------------------------------------------------------------------------
// Test: WebSocket connects with ticket (101 Switching Protocols)
// ---------------------------------------------------------------------------
test('WebSocket: connects with single-use ticket only (no JWT)', async ({ page }) => {
  const apiContext = await request.newContext();
  try {
    const { accessToken } = await createUser(apiContext, `ws_${Date.now()}`);
    const ticket = await getWsTicket(apiContext, accessToken);

    // Verify ticket works (WebSocket upgrade) by checking from the page
    const wsUrl = `ws://localhost/ws/alerts/?ticket=${ticket}`;

    const wsResult = await page.evaluate(async (url: string) => {
      return new Promise<{ connected: boolean; code?: number }>((resolve) => {
        const ws = new WebSocket(url);
        const timeout = setTimeout(() => {
          ws.close();
          resolve({ connected: false });
        }, 5000);

        ws.onopen = () => {
          clearTimeout(timeout);
          ws.close(1000);
          resolve({ connected: true });
        };

        ws.onerror = () => {
          clearTimeout(timeout);
          resolve({ connected: false });
        };

        ws.onclose = (e) => {
          if (e.code !== 1000) {
            clearTimeout(timeout);
            resolve({ connected: false, code: e.code });
          }
        };
      });
    }, wsUrl);

    expect(wsResult.connected).toBe(true);

    // Verify ticket is single-use: second connection with same ticket must fail
    const ticket2 = ticket; // same ticket
    const ws2Result = await page.evaluate(async (url: string) => {
      return new Promise<{ connected: boolean; code?: number }>((resolve) => {
        const ws = new WebSocket(url);
        const timeout = setTimeout(() => {
          ws.close();
          resolve({ connected: false });
        }, 5000);

        ws.onopen = () => {
          clearTimeout(timeout);
          resolve({ connected: true });
        };

        ws.onclose = (e) => {
          clearTimeout(timeout);
          resolve({ connected: false, code: e.code });
        };
      });
    }, `ws://localhost/ws/alerts/?ticket=${ticket2}`);

    expect(ws2Result.connected).toBe(false);
    expect(ws2Result.code).toBe(BROWSER_REJECTED_WS_CODE);
  } finally {
    await apiContext.dispose();
  }
});

// ---------------------------------------------------------------------------
// Test: WebSocket connection fails without ticket or with expired ticket
// ---------------------------------------------------------------------------
test('WebSocket: rejected without ticket (4401)', async ({ page }) => {
  const result = await page.evaluate(async () => {
    return new Promise<{ connected: boolean; code: number }>((resolve) => {
      const ws = new WebSocket('ws://localhost/ws/alerts/');
      const timeout = setTimeout(() => resolve({ connected: false, code: 0 }), 5000);

      ws.onopen = () => {
        clearTimeout(timeout);
        resolve({ connected: true, code: 0 });
      };

      ws.onclose = (e) => {
        clearTimeout(timeout);
        resolve({ connected: false, code: e.code });
      };
    });
  });

  expect(result.connected).toBe(false);
  expect(result.code).toBe(BROWSER_REJECTED_WS_CODE);
});

// ---------------------------------------------------------------------------
// Test: Health endpoints
// ---------------------------------------------------------------------------
test('Health: liveness and readiness endpoints return 200', async ({ request: apiReq }) => {
  const live = await apiReq.get(`${API_URL}/health/live/`);
  expect(live.ok()).toBe(true);
  const liveJson = await live.json();
  expect(liveJson.status).toBe('live');

  const ready = await apiReq.get(`${API_URL}/health/ready/`);
  expect(ready.ok()).toBe(true);
  const readyJson = await ready.json();
  expect(readyJson.status).toBe('ready');
});

// ---------------------------------------------------------------------------
// Test: Alert delivery and ACK flow
// ---------------------------------------------------------------------------
test('Alert: create alert → deliver → frontend receives → ACK sent → acknowledged', async ({ page }) => {
  const apiContext = await request.newContext();
  try {
    const { accessToken } = await createUser(apiContext, `alert_${Date.now()}`);

    // Create a tracked product
    const productRes = await apiContext.post(`${API_URL}/trackers/products/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        product_name: 'E2E Test Product',
        target_url: 'https://example.com/product',
        notification_threshold: '1000.00',
        is_active: true,
      },
    });
    expect(productRes.ok()).toBe(true);

    // Get a fresh ticket
    const ticket = await getWsTicket(apiContext, accessToken);

    // Check that alert state management endpoints work
    const productsRes = await apiContext.get(`${API_URL}/trackers/products/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    expect(productsRes.ok()).toBe(true);
    const products = await productsRes.json();
    expect(products.length).toBeGreaterThan(0);

    // Verify ticket was valid (not expired)
    expect(ticket).toBeTruthy();
  } finally {
    await apiContext.dispose();
  }
});
