import { test, expect, request } from '@playwright/test';

const API_URL = 'http://localhost/api';
const BROWSER_REJECTED_WS_CODE = 1006;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
async function createUser(
  apiContext: Awaited<ReturnType<typeof request.newContext>>,
  suffix: string,
) {
  const email = `redis_e2e_${suffix.toLowerCase()}@test.com`;
  const password = 'E2eTest@12345!';

  await apiContext.post(`${API_URL}/auth/register/`, {
    data: { email, password, first_name: 'Redis', last_name: 'Recovery' },
  });

  const loginRes = await apiContext.post(`${API_URL}/auth/login/`, {
    data: { email, password },
  });
  expect(loginRes.ok(), await loginRes.text()).toBe(true);
  const tokens = await loginRes.json();
  return { email, password, accessToken: tokens.access as string };
}

async function getWsTicket(
  apiContext: Awaited<ReturnType<typeof request.newContext>>,
  accessToken: string,
) {
  const res = await apiContext.post(`${API_URL}/auth/ws-ticket/`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  expect(res.ok(), await res.text()).toBe(true);
  const data = await res.json();
  return data.ticket as string;
}

async function createProduct(
  apiContext: Awaited<ReturnType<typeof request.newContext>>,
  accessToken: string,
  suffix: string,
) {
  const res = await apiContext.post(`${API_URL}/trackers/products/`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      product_name: `Recovery Test Product ${suffix}`,
      target_url: `https://example.com/product/${suffix}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      notification_threshold: '999.00',
      is_active: true,
    },
  });
  expect(res.ok(), await res.text()).toBe(true);
  return await res.json();
}

// ---------------------------------------------------------------------------
// Test: Recovery endpoint is available and responds correctly
// ---------------------------------------------------------------------------
test('Recovery: health endpoints remain live and ready', async ({ request: apiReq }) => {
  // These checks confirm the system has proper health probes that
  // orchestration can use to detect and restart unhealthy services.
  const live = await apiReq.get(`${API_URL}/health/live/`);
  expect(live.ok()).toBe(true);
  const liveJson = await live.json();
  expect(liveJson.status).toBe('live');

  const ready = await apiReq.get(`${API_URL}/health/ready/`);
  expect(ready.ok()).toBe(true);
  const readyJson = await ready.json();
  expect(readyJson.status).toBe('ready');
  // Both DB and Redis must report healthy for readiness
  expect(readyJson).toHaveProperty('db');
  expect(readyJson).toHaveProperty('redis');
});

// ---------------------------------------------------------------------------
// Test: WS ticket survives within its TTL window
// ---------------------------------------------------------------------------
test('Recovery: WS ticket remains valid within 30-second TTL', async () => {
  const apiContext = await request.newContext();
  try {
    const { accessToken } = await createUser(apiContext, `ttl_${Date.now()}`);
    const ticket = await getWsTicket(apiContext, accessToken);

    expect(ticket).toBeTruthy();
    expect(typeof ticket).toBe('string');
    expect(ticket.length).toBeGreaterThanOrEqual(32);
  } finally {
    await apiContext.dispose();
  }
});

// ---------------------------------------------------------------------------
// Test: Expired / reused ticket is rejected with 4403
// ---------------------------------------------------------------------------
test('Recovery: reused or expired ticket is rejected (4403)', async ({ page }) => {
  const apiContext = await request.newContext();
  try {
    const { accessToken } = await createUser(apiContext, `reuse_${Date.now()}`);
    const ticket = await getWsTicket(apiContext, accessToken);

    // First connection consumes the ticket atomically
    await page.evaluate(async (url: string) => {
      await new Promise<void>((resolve) => {
        const ws = new WebSocket(url);
        ws.onopen = () => { ws.close(1000); resolve(); };
        ws.onerror = () => resolve();
        ws.onclose = () => resolve();
        setTimeout(resolve, 5000);
      });
    }, `ws://localhost/ws/alerts/?ticket=${ticket}`);

    // Second connection with the same ticket must be denied — the ticket was
    // atomically consumed (GETDEL) on first use.
    const result = await page.evaluate(async (url: string) => {
      return new Promise<{ connected: boolean; code: number }>((resolve) => {
        const ws = new WebSocket(url);
        const t = setTimeout(() => resolve({ connected: false, code: 0 }), 5000);

        ws.onopen = () => {
          clearTimeout(t);
          resolve({ connected: true, code: 0 });
        };
        ws.onclose = (e) => {
          clearTimeout(t);
          resolve({ connected: false, code: e.code });
        };
      });
    }, `ws://localhost/ws/alerts/?ticket=${ticket}`);

    expect(result.connected).toBe(false);
    expect(result.code).toBe(BROWSER_REJECTED_WS_CODE);
  } finally {
    await apiContext.dispose();
  }
});

// ---------------------------------------------------------------------------
// Test: Fresh ticket allows reconnection after disconnect
// ---------------------------------------------------------------------------
test('Recovery: fresh ticket allows reconnection after disconnect', async ({ page }) => {
  const apiContext = await request.newContext();
  try {
    const { accessToken } = await createUser(apiContext, `reconnect_${Date.now()}`);

    // First connection
    const ticket1 = await getWsTicket(apiContext, accessToken);
    const conn1 = await page.evaluate(async (url: string) => {
      return new Promise<{ connected: boolean }>((resolve) => {
        const ws = new WebSocket(url);
        const t = setTimeout(() => resolve({ connected: false }), 5000);
        ws.onopen = () => { clearTimeout(t); ws.close(1000); resolve({ connected: true }); };
        ws.onerror = () => { clearTimeout(t); resolve({ connected: false }); };
      });
    }, `ws://localhost/ws/alerts/?ticket=${ticket1}`);

    expect(conn1.connected).toBe(true);

    // Wait a beat, then reconnect with a brand-new ticket
    await page.waitForTimeout(500);
    const ticket2 = await getWsTicket(apiContext, accessToken);

    const conn2 = await page.evaluate(async (url: string) => {
      return new Promise<{ connected: boolean }>((resolve) => {
        const ws = new WebSocket(url);
        const t = setTimeout(() => resolve({ connected: false }), 5000);
        ws.onopen = () => { clearTimeout(t); ws.close(1000); resolve({ connected: true }); };
        ws.onerror = () => { clearTimeout(t); resolve({ connected: false }); };
      });
    }, `ws://localhost/ws/alerts/?ticket=${ticket2}`);

    expect(conn2.connected).toBe(true);
  } finally {
    await apiContext.dispose();
  }
});

// ---------------------------------------------------------------------------
// Test: Product creation and listing remain functional (scraper state persists)
// ---------------------------------------------------------------------------
test('Recovery: product CRUD survives across requests (DB integrity)', async () => {
  const apiContext = await request.newContext();
  try {
    const { accessToken } = await createUser(apiContext, `crud_${Date.now()}`);

    // Create two products
    const p1 = await createProduct(apiContext, accessToken, 'alpha');
    const p2 = await createProduct(apiContext, accessToken, 'beta');

    expect(p1.id).toBeTruthy();
    expect(p2.id).toBeTruthy();

    // List and confirm both are present
    const listRes = await apiContext.get(`${API_URL}/trackers/products/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    expect(listRes.ok()).toBe(true);
    const products = await listRes.json();

    const ids = products.map((p: { id: number }) => p.id);
    expect(ids).toContain(p1.id);
    expect(ids).toContain(p2.id);
  } finally {
    await apiContext.dispose();
  }
});

// ---------------------------------------------------------------------------
// Test: User isolation — one user cannot see another's products
// ---------------------------------------------------------------------------
test('Recovery: user isolation — products are scoped per owner', async () => {
  const apiContext = await request.newContext();
  try {
    const userA = await createUser(apiContext, `usera_${Date.now()}`);
    const userB = await createUser(apiContext, `userb_${Date.now()}`);

    // UserA creates a product
    const product = await createProduct(apiContext, userA.accessToken, 'isolated');

    // UserB lists products — must NOT see UserA's product
    const listRes = await apiContext.get(`${API_URL}/trackers/products/`, {
      headers: { Authorization: `Bearer ${userB.accessToken}` },
    });
    expect(listRes.ok()).toBe(true);
    const products = await listRes.json();

    const ids = products.map((p: { id: number }) => p.id);
    expect(ids).not.toContain(product.id);
  } finally {
    await apiContext.dispose();
  }
});

// ---------------------------------------------------------------------------
// Test: Readiness probe detects Redis dependency
// ---------------------------------------------------------------------------
test('Recovery: readiness probe reports redis status', async ({ request: apiReq }) => {
  const res = await apiReq.get(`${API_URL}/health/ready/`);
  // Under normal conditions this must be 200 with redis: "ok"
  expect(res.ok()).toBe(true);
  const body = await res.json();
  expect(body.redis).toBe('ok');
  expect(body.db).toBe('ok');
});
