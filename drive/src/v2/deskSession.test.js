import test from "node:test";
import assert from "node:assert/strict";
import {
  clearDeskToken,
  deskFetchInit,
  deskHeaders,
  deskSessionBootstrapped,
  hasDeskToken,
  markDeskSessionBootstrapped,
  saveDeskToken,
} from "./deskSession.js";

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
}

installMemorySessionStorage();

test("saveDeskToken persists for deskHeaders without exposing empty tokens", () => {
  clearDeskToken();
  assert.equal(hasDeskToken(), false);
  assert.equal(deskHeaders()["x-desk-token"], undefined);
  saveDeskToken("unit-test-token");
  assert.equal(hasDeskToken(), true);
  assert.equal(deskHeaders()["x-desk-token"], "unit-test-token");
  clearDeskToken();
  assert.equal(hasDeskToken(), false);
});

test("deskFetchInit always includes credentials for cookie sessions", () => {
  const init = deskFetchInit({ method: "POST", body: "{}" });
  assert.equal(init.credentials, "include");
  assert.equal(init.headers["content-type"], "application/json");
});

test("markDeskSessionBootstrapped tracks cookie bootstrap state", () => {
  markDeskSessionBootstrapped(false);
  assert.equal(deskSessionBootstrapped(), false);
  markDeskSessionBootstrapped(true);
  assert.equal(deskSessionBootstrapped(), true);
  markDeskSessionBootstrapped(false);
  assert.equal(deskSessionBootstrapped(), false);
});
