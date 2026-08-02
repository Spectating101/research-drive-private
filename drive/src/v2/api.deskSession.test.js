import assert from "node:assert/strict";
import test, { afterEach, beforeEach } from "node:test";

import {
  clearDeskSession,
  deskCapabilities,
  deskWarm,
  ensureDeskAccess,
  ensureDeskSession,
  fetchJson,
} from "./api.js";
import { deskSessionBootstrapped, markDeskSessionBootstrapped } from "./deskSession.js";

function installMemorySessionStorage() {
  const store = new Map();
  globalThis.sessionStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => {
      store.set(String(k), String(v));
    },
    removeItem: (k) => {
      store.delete(String(k));
    },
  };
  return store;
}

function installMemoryLocalStorage() {
  const store = new Map();
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => {
      store.set(String(k), String(v));
    },
    removeItem: (k) => {
      store.delete(String(k));
    },
  };
}

function mockResponse(body, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    async text() {
      return typeof body === "string" ? body : JSON.stringify(body);
    },
    async json() {
      return typeof body === "string" ? JSON.parse(body || "{}") : body;
    },
  };
}

let fetchCalls = [];
let originalFetch;

beforeEach(() => {
  installMemorySessionStorage();
  installMemoryLocalStorage();
  markDeskSessionBootstrapped(false);
  fetchCalls = [];
  originalFetch = globalThis.fetch;
});

afterEach(async () => {
  // Reset module inflight + bootstrap flag without touching a real network.
  globalThis.fetch = async () => mockResponse({ ok: true });
  markDeskSessionBootstrapped(false);
  await clearDeskSession();
  globalThis.fetch = originalFetch;
});

test("ensureDeskSession deduplicates concurrent bootstrap POSTs", async () => {
  let resolveSession;
  const sessionGate = new Promise((resolve) => {
    resolveSession = resolve;
  });
  let sessionPosts = 0;

  globalThis.fetch = async (url, init = {}) => {
    fetchCalls.push({ url: String(url), method: init.method || "GET", init });
    if (String(url).includes("/library/desk/session")) {
      sessionPosts += 1;
      await sessionGate;
      return mockResponse({ ok: true, authorized: true });
    }
    return mockResponse({ ok: true });
  };

  const a = ensureDeskSession();
  const b = ensureDeskSession();
  assert.equal(sessionPosts, 1);
  resolveSession();
  const [ra, rb] = await Promise.all([a, b]);
  assert.equal(ra.ok, true);
  assert.equal(rb.ok, true);
  assert.equal(sessionPosts, 1);
  assert.equal(deskSessionBootstrapped(), true);
  assert.equal(fetchCalls.every((c) => c.init?.credentials === "include"), true);
});

test("deskWarm waits for session then POSTs warm with credentials", async () => {
  const order = [];
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url);
    fetchCalls.push({ url: path, method: init.method || "GET", init });
    if (path.includes("/library/desk/session")) {
      order.push("session");
      return mockResponse({ ok: true, authorized: true });
    }
    if (path.includes("/library/desk/warm")) {
      order.push("warm");
      return mockResponse({ ok: true, warmed: true });
    }
    return mockResponse({ ok: true });
  };

  const out = await deskWarm({ sessionId: "s1", userEmail: "a@b.c", background: true });
  assert.equal(out.ok, true);
  assert.deepEqual(order, ["session", "warm"]);
  assert.equal(fetchCalls.length, 2);
  assert.match(fetchCalls[0].url, /\/library\/desk\/session$/);
  assert.equal(fetchCalls[0].method, "POST");
  assert.equal(fetchCalls[0].init.credentials, "include");
  assert.match(fetchCalls[1].url, /\/library\/desk\/warm$/);
  assert.equal(fetchCalls[1].method, "POST");
  assert.equal(fetchCalls[1].init.credentials, "include");
  const warmBody = JSON.parse(fetchCalls[1].init.body);
  assert.equal(warmBody.session_id, "s1");
  assert.equal(warmBody.user_email, "a@b.c");
});

test("deskWarm skips warm POST when bootstrap fails", async () => {
  globalThis.fetch = async (url, init = {}) => {
    fetchCalls.push({ url: String(url), method: init.method || "GET", init });
    if (String(url).includes("/library/desk/session")) {
      return mockResponse({ detail: "unauthorized" }, { ok: false, status: 401 });
    }
    return mockResponse({ ok: true, warmed: true });
  };

  const out = await deskWarm({ background: true });
  assert.equal(out.ok, false);
  assert.equal(out.skipped, true);
  assert.equal(out.reason, "desk_session_unavailable");
  assert.ok(out.error);
  assert.equal(fetchCalls.length, 1);
  assert.match(fetchCalls[0].url, /\/library\/desk\/session$/);
  assert.equal(
    fetchCalls.some((c) => String(c.url).includes("/library/desk/warm")),
    false,
  );
  assert.equal(deskSessionBootstrapped(), false);
});

test("concurrent deskWarm callers share one session bootstrap and may each warm", async () => {
  let resolveSession;
  const sessionGate = new Promise((resolve) => {
    resolveSession = resolve;
  });
  let sessionPosts = 0;
  let warmPosts = 0;

  globalThis.fetch = async (url, init = {}) => {
    fetchCalls.push({ url: String(url), method: init.method || "GET", init });
    if (String(url).includes("/library/desk/session")) {
      sessionPosts += 1;
      await sessionGate;
      return mockResponse({ ok: true, authorized: true });
    }
    if (String(url).includes("/library/desk/warm")) {
      warmPosts += 1;
      return mockResponse({ ok: true });
    }
    return mockResponse({ ok: true });
  };

  const warmA = deskWarm({ background: true });
  const warmB = deskWarm({ background: true });
  assert.equal(sessionPosts, 1);
  assert.equal(warmPosts, 0);
  resolveSession();
  const [a, b] = await Promise.all([warmA, warmB]);
  assert.equal(a.ok, true);
  assert.equal(b.ok, true);
  assert.equal(sessionPosts, 1);
  assert.equal(warmPosts, 2);
});

test("reused bootstrapped session does not re-POST /library/desk/session before warm", async () => {
  markDeskSessionBootstrapped(true);
  globalThis.fetch = async (url, init = {}) => {
    fetchCalls.push({ url: String(url), method: init.method || "GET", init });
    if (String(url).includes("/library/desk/warm")) {
      return mockResponse({ ok: true });
    }
    return mockResponse({ ok: true, authorized: true });
  };

  const out = await deskWarm({ background: true });
  assert.equal(out.ok, true);
  assert.equal(fetchCalls.length, 1);
  assert.match(fetchCalls[0].url, /\/library\/desk\/warm$/);
});

test("protected GET retries once after transparent session bootstrap", async () => {
  let datasetsCalls = 0;
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url);
    fetchCalls.push({ url: path, method: init.method || "GET", init });
    if (path.endsWith("/datasets")) {
      datasetsCalls += 1;
      if (datasetsCalls === 1) {
        return mockResponse(
          { error: "Unauthorized", message: "Desk access token required" },
          { ok: false, status: 401 },
        );
      }
      return mockResponse({ datasets: [{ dataset_id: "private-panel" }] });
    }
    if (path.endsWith("/library/desk/session")) {
      return mockResponse({ ok: true, authorized: true });
    }
    throw new Error(`unexpected request ${path}`);
  };

  const out = await fetchJson("/datasets");
  assert.equal(out.datasets[0].dataset_id, "private-panel");
  assert.deepEqual(
    fetchCalls.map((call) => call.url.replace(/^.*(?=\/)/, "")),
    ["/datasets", "/session", "/datasets"],
  );
  assert.equal(deskSessionBootstrapped(), true);
});

test("capability document stays public and reports a locked browser", async () => {
  globalThis.fetch = async (url, init = {}) => {
    fetchCalls.push({ url: String(url), method: init.method || "GET", init });
    return mockResponse({
      version: 2,
      authenticated: false,
      access: "locked",
      permissions: { use_ask: false, approve_jobs: false },
    });
  };

  const out = await deskCapabilities();
  assert.equal(out.authenticated, false);
  assert.equal(fetchCalls.length, 1);
  assert.match(fetchCalls[0].url, /\/library\/desk\/capabilities$/);
});

test("authenticated v1 capability retains the former operator permission contract", async () => {
  globalThis.fetch = async () => mockResponse({ version: 1, authenticated: true, access: "operator" });
  const out = await deskCapabilities();
  assert.equal(out.permissions.use_ask, true);
  assert.equal(out.permissions.approve_jobs, true);
});

test("ensureDeskAccess rechecks capabilities after a successful mint", async () => {
  let capabilityCalls = 0;
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url);
    fetchCalls.push({ url: path, method: init.method || "GET", init });
    if (path.endsWith("/library/desk/capabilities")) {
      capabilityCalls += 1;
      return mockResponse({
        version: 2,
        authenticated: capabilityCalls > 1,
        access: capabilityCalls > 1 ? "operator" : "locked",
        principal: capabilityCalls > 1
          ? {
              id: "researcher-1",
              email: "researcher@example.test",
              display_name: "Researcher One",
              role: "researcher",
              default_workspace_id: "methods-lab",
            }
          : null,
      });
    }
    if (path.endsWith("/library/desk/session")) {
      return mockResponse({ ok: true, authorized: true });
    }
    throw new Error(`unexpected request ${path}`);
  };

  const out = await ensureDeskAccess();
  assert.equal(out.authenticated, true);
  assert.equal(out.principal.id, "researcher-1");
  assert.equal(out.principal.default_workspace_id, "methods-lab");
  assert.equal(capabilityCalls, 2);
  assert.equal(fetchCalls.length, 3);
});
