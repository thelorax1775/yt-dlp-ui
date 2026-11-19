// Preloaded into `next start` by scripts/smoke.mjs (NODE_OPTIONS=--require).
// Every attempt to open a socket to a non-loopback host is written to
// $SMOKE_EGRESS_LOG and refused, so the smoke test can prove the server made
// no outbound request.
const fs = require("node:fs");
const net = require("node:net");

const logFile = process.env.SMOKE_EGRESS_LOG;
const LOOPBACK = /^(localhost|127\.\d+\.\d+\.\d+|::1|::ffff:127\.\d+\.\d+\.\d+)$/i;

function target(args) {
  let first = args[0];
  if (Array.isArray(first)) first = first[0]; // net's normalized-args form
  if (first && typeof first === "object") {
    if (first.path) return null; // unix socket
    return first.host || first.hostname || "localhost";
  }
  if (typeof first === "string") return null; // unix socket path
  return typeof args[1] === "string" ? args[1] : "localhost";
}

const realConnect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function guardedConnect(...args) {
  const host = target(args);
  if (host !== null && !LOOPBACK.test(host)) {
    if (logFile) fs.appendFileSync(logFile, `${host}\n`);
    process.nextTick(() =>
      this.destroy(new Error(`egress-guard: blocked connection to ${host}`)),
    );
    return this;
  }
  return realConnect.apply(this, args);
};
