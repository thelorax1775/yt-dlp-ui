#!/usr/bin/env node
// Smoke test for the production server (`npm run test:smoke`).
//
// Builds the app with BACKEND_URL pointed at a tiny fake backend, runs
// `next start`, and checks that:
//   1. GET /api/health through the frontend returns the fake backend's answer
//      (the /api rewrite still works),
//   2. the pages render,
//   3. GET /_next/image?url=<remote> answers 400/404 and the server opens no
//      connection to any non-loopback host (the image optimizer is off).
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, existsSync, rmSync } from "node:fs";
import http from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const nextBin = path.join(root, "node_modules", "next", "dist", "bin", "next");
const guard = path.join(root, "scripts", "egress-guard.cjs");
const HEALTH = { status: "ok", from: "fake-backend" };

function listen(server) {
  return new Promise((resolve) =>
    server.listen(0, "127.0.0.1", () => resolve(server.address().port)),
  );
}

async function freePort() {
  const s = http.createServer();
  const port = await listen(s);
  await new Promise((r) => s.close(r));
  return port;
}

async function waitFor(url, child, ms = 60_000) {
  const deadline = Date.now() + ms;
  for (;;) {
    if (child.exitCode !== null) throw new Error("next start exited early");
    try {
      await fetch(url);
      return;
    } catch {
      if (Date.now() > deadline) throw new Error(`timed out waiting for ${url}`);
      await new Promise((r) => setTimeout(r, 250));
    }
  }
}

const backendHits = [];
const backend = http.createServer((req, res) => {
  backendHits.push(req.url);
  if (req.url === "/api/health") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(HEALTH));
  } else {
    res.writeHead(404).end();
  }
});
const backendPort = await listen(backend);
const frontPort = await freePort();
const tmp = mkdtempSync(path.join(tmpdir(), "ytdlp-ui-smoke-"));
const egressLog = path.join(tmp, "egress.log");
const env = {
  ...process.env,
  NODE_ENV: "production",
  NEXT_TELEMETRY_DISABLED: "1",
  BACKEND_URL: `http://127.0.0.1:${backendPort}`,
};

let child;
try {
  // BACKEND_URL is baked into the build, so build with the fake's address.
  const build = spawnSync(process.execPath, [nextBin, "build"], {
    cwd: root,
    env,
    stdio: "inherit",
  });
  assert.equal(build.status, 0, "next build failed");

  child = spawn(
    process.execPath,
    [nextBin, "start", "-H", "127.0.0.1", "-p", String(frontPort)],
    {
      cwd: root,
      env: {
        ...env,
        SMOKE_EGRESS_LOG: egressLog,
        NODE_OPTIONS: `--require ${JSON.stringify(guard)}`,
      },
      stdio: "inherit",
    },
  );
  const base = `http://127.0.0.1:${frontPort}`;
  await waitFor(`${base}/`, child);

  // 1. /api rewrite reaches the backend.
  const health = await fetch(`${base}/api/health`);
  assert.equal(health.status, 200, "/api/health status");
  assert.deepEqual(await health.json(), HEALTH, "/api/health body");
  assert.ok(backendHits.includes("/api/health"), "backend saw /api/health");

  // 2. Pages render.
  for (const page of ["/", "/downloads", "/history", "/files", "/settings"]) {
    const res = await fetch(`${base}${page}`);
    assert.equal(res.status, 200, `${page} status`);
  }

  // 3. The image optimizer is off and fetches nothing.
  const hitsBefore = backendHits.length;
  const remotes = [
    "https://example.com/",
    "https://example.com/a.png",
    `http://127.0.0.1:${backendPort}/img.png`,
  ];
  for (const remote of remotes) {
    const url = `${base}/_next/image?url=${encodeURIComponent(remote)}&w=64&q=75`;
    const res = await fetch(url);
    assert.ok(
      res.status === 400 || res.status === 404,
      `/_next/image for ${remote} answered ${res.status}, want 400 or 404`,
    );
  }
  // Give a (wrongly) started upstream fetch time to show up.
  await new Promise((r) => setTimeout(r, 1500));
  assert.equal(backendHits.length, hitsBefore, "image endpoint fetched from the backend");
  const egress = existsSync(egressLog) ? readFileSync(egressLog, "utf8").trim() : "";
  assert.equal(egress, "", `server opened outbound connections: ${egress}`);

  console.log("smoke: ok (api rewrite works, pages render, /_next/image is off, no egress)");
} finally {
  if (child && child.exitCode === null) {
    child.kill("SIGTERM");
    await new Promise((r) => child.once("exit", r));
  }
  await new Promise((r) => backend.close(r));
  rmSync(tmp, { recursive: true, force: true });
}
