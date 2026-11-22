import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import { api } from "../lib/api.ts";

const originalFetch = globalThis.fetch;

function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    statusText: ok ? "OK" : "Not Found",
    json: async () => body,
  };
}

beforeEach(() => {
  globalThis.fetch = async () => jsonResponse([]);
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

test("deleteHistoryEntry sends DELETE to the entry URL and returns the body", async () => {
  let calledUrl;
  let calledOptions;
  globalThis.fetch = async (url, options) => {
    calledUrl = url;
    calledOptions = options;
    return jsonResponse({ status: "deleted", id: "7" });
  };

  const result = await api.deleteHistoryEntry("7");

  assert.equal(calledUrl, "/api/history/7");
  assert.equal(calledOptions.method, "DELETE");
  assert.deepEqual(result, { status: "deleted", id: "7" });
});

test("clearHistory sends DELETE to the history URL", async () => {
  let calledUrl;
  let calledOptions;
  globalThis.fetch = async (url, options) => {
    calledUrl = url;
    calledOptions = options;
    return jsonResponse({ status: "cleared", count: 3 });
  };

  const result = await api.clearHistory();

  assert.equal(calledUrl, "/api/history");
  assert.equal(calledOptions.method, "DELETE");
  assert.deepEqual(result, { status: "cleared", count: 3 });
});

test("deleteHistoryEntry rejects with the backend error detail", async () => {
  globalThis.fetch = async () =>
    jsonResponse(
      { detail: "History entry not found" },
      { ok: false, status: 404 }
    );

  await assert.rejects(
    () => api.deleteHistoryEntry("missing"),
    (error) =>
      error instanceof Error && error.message === "History entry not found"
  );
});

test("getHistory sends GET to the history URL", async () => {
  let calledUrl;
  let calledOptions;
  globalThis.fetch = async (url, options) => {
    calledUrl = url;
    calledOptions = options;
    return jsonResponse([]);
  };

  await api.getHistory();

  assert.equal(calledUrl, "/api/history");
  assert.equal(calledOptions, undefined);
});
