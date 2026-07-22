/**
 * Local vite desk proxy — token injection must never leak values into assertions.
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { buildDeskProxyMap, readLocalDeskToken, withLocalDeskAuth } from "./vite.deskProxy.js";

test("withLocalDeskAuth keeps changeOrigin false for Host/origin session bootstrap", () => {
  const cfg = withLocalDeskAuth({ target: "http://100.127.141.44:8765" });
  assert.equal(cfg.changeOrigin, false);
  assert.equal(typeof cfg.configure, "function");
});

test("buildDeskProxyMap wires /api rewrite and library routes", () => {
  const map = buildDeskProxyMap("http://100.127.141.44:8765");
  assert.equal(typeof map["/api"].rewrite, "function");
  assert.equal(map["/api"].rewrite("/api/library/chat"), "/library/chat");
  assert.equal(map["/library"].target, "http://100.127.141.44:8765");
  assert.equal(map["/library"].changeOrigin, false);
});

test("readLocalDeskToken returns empty string when file missing", () => {
  const prev = process.env.YZU_DESK_TOKEN_FILE;
  process.env.YZU_DESK_TOKEN_FILE = path.join(os.tmpdir(), `missing-desk-token-${Date.now()}`);
  try {
    assert.equal(readLocalDeskToken(), "");
  } finally {
    if (prev === undefined) delete process.env.YZU_DESK_TOKEN_FILE;
    else process.env.YZU_DESK_TOKEN_FILE = prev;
  }
});

test("proxyReq injects Authorization only when browser omitted credentials", () => {
  const tmp = path.join(os.tmpdir(), `desk-token-${Date.now()}.txt`);
  fs.writeFileSync(tmp, "unit-local-desk-token\n", "utf8");
  const prev = process.env.YZU_DESK_TOKEN_FILE;
  process.env.YZU_DESK_TOKEN_FILE = tmp;

  const headers = {};
  const proxyReq = {
    getHeader(name) {
      return headers[String(name).toLowerCase()];
    },
    setHeader(name, value) {
      headers[String(name).toLowerCase()] = value;
    },
  };

  try {
    const cfg = withLocalDeskAuth({ target: "http://example.test" });
    const fakeProxy = {
      on(event, fn) {
        if (event === "proxyReq") fn(proxyReq);
      },
    };
    cfg.configure(fakeProxy);
    assert.equal(headers.authorization, "Bearer unit-local-desk-token");

    // Second pass: browser already sent a header — do not overwrite.
    headers.authorization = "Bearer browser-provided";
    cfg.configure({
      on(event, fn) {
        if (event === "proxyReq") fn(proxyReq);
      },
    });
    assert.equal(headers.authorization, "Bearer browser-provided");
  } finally {
    fs.unlinkSync(tmp);
    if (prev === undefined) delete process.env.YZU_DESK_TOKEN_FILE;
    else process.env.YZU_DESK_TOKEN_FILE = prev;
  }
});
